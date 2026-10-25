from collections.abc import Callable, Iterator
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import Product, ProductNote, ProductTag, User, Workspace

# The context rail's notes and tags (UX-4, DEC-243): workspace-owned rows on global products.

As = Callable[[str], TestClient]


@pytest.fixture
def rail(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, UUID]]:
    """`as_("a")` makes the next requests workspace A's; ids holds the products."""
    with Session(db_engine) as session:
        users = {key: User(clerk_user_id=f"user_{key}") for key in "ab"}
        workspaces = {key: Workspace(name=f"Workspace {key}") for key in "ab"}
        survivor = Product(name="Survivor")
        session.add_all([*users.values(), *workspaces.values(), survivor])
        session.flush()
        merged = Product(name="Merged", merged_into_id=survivor.id)
        session.add(merged)
        session.commit()
        principals = {key: Principal(users[key].id, workspaces[key].id) for key in "ab"}
        ids = {"product": survivor.id, "merged": merged.id}

    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    app = client.app
    app.dependency_overrides[get_db] = database

    def as_(key: str) -> TestClient:
        app.dependency_overrides[current_principal] = lambda: principals[key]
        return client

    return as_, ids


@pytest.mark.db
def test_notes_list_newest_first_in_pages(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    url = f"/v1/products/{ids['product']}/notes"
    created = []
    for body in ("first", "  second\n", "third"):
        response = as_("a").post(url, json={"body": body})
        assert response.status_code == 201
        created.append(response.json())
    assert created[1]["body"] == "second"  # trimmed
    assert created[0]["created_at"] < created[1]["created_at"] < created[2]["created_at"]

    page = as_("a").get(url, params={"limit": 2}).json()
    assert [note["body"] for note in page["items"]] == ["third", "second"]
    assert page["items"][0] == created[2]
    rest = as_("a").get(url, params={"limit": 2, "cursor": page["next_cursor"]}).json()
    assert ([note["body"] for note in rest["items"]], rest["next_cursor"]) == (["first"], None)


@pytest.mark.db
def test_notes_reject_bad_input(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    client = as_("a")
    url = f"/v1/products/{ids['product']}/notes"
    for body in ({"body": "   "}, {"body": "x" * 10_001}, {"body": "x", "pinned": True}, {}):
        assert client.post(url, json=body).status_code == 422, body
    response = client.get(url, params={"cursor": "not-json"})
    assert (response.status_code, response.json()["code"]) == (422, "invalid_cursor")
    assert client.get(url, params={"limit": 101}).status_code == 422
    unknown = f"/v1/products/{uuid4()}/notes"
    assert client.get(unknown).status_code == client.post(unknown, json={"body": "x"}).status_code
    assert client.get(unknown).status_code == 404
    # A merge that lands while the page is open: never write to the merged product.
    merged = client.post(f"/v1/products/{ids['merged']}/notes", json={"body": "x"})
    assert (merged.status_code, merged.json()["code"]) == (409, "merged")
    assert client.get(url).json()["items"] == []


@pytest.mark.db
def test_tags_put_replaces_the_set(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    client = as_("a")
    url = f"/v1/products/{ids['product']}/tags"
    assert client.get(url).json() == {"tags": []}
    response = client.put(url, json={"tags": ["  Winner ", "q4   test", "winner", "TikTok"]})
    assert response.status_code == 200
    # Trimmed, inner spaces collapsed, a case-only repeat dropped, sorted case-insensitively.
    assert response.json() == {"tags": ["q4 test", "TikTok", "Winner"]}
    assert client.get(url).json() == response.json()
    assert client.put(url, json={"tags": ["TikTok"]}).json() == {"tags": ["TikTok"]}
    assert client.put(url, json={"tags": []}).json() == {"tags": []}
    for tags in ([f"t{i}" for i in range(21)], ["x" * 81], [" "]):
        assert client.put(url, json={"tags": tags}).status_code == 422
    assert client.put(f"/v1/products/{uuid4()}/tags", json={"tags": []}).status_code == 404
    merged = client.put(f"/v1/products/{ids['merged']}/tags", json={"tags": ["x"]})
    assert merged.status_code == 409


@pytest.mark.db
def test_workspace_b_never_sees_or_edits_a(
    rail: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = rail
    notes = f"/v1/products/{ids['product']}/notes"
    tags = f"/v1/products/{ids['product']}/tags"
    as_("a").post(notes, json={"body": "A's private take"})
    as_("a").put(tags, json={"tags": ["mine"]})

    assert as_("b").get(notes).json() == {"items": [], "next_cursor": None}
    assert as_("b").get(tags).json() == {"tags": []}
    assert as_("b").put(tags, json={"tags": ["theirs"]}).json() == {"tags": ["theirs"]}
    assert as_("b").put(tags, json={"tags": []}).json() == {"tags": []}  # clears only B's

    assert [note["body"] for note in as_("a").get(notes).json()["items"]] == ["A's private take"]
    assert as_("a").get(tags).json() == {"tags": ["mine"]}
    with Session(db_engine) as session:
        assert session.execute(select(ProductTag.tag)).scalars().all() == ["mine"]


@pytest.mark.db
def test_notes_and_tags_on_a_merged_product_read_through_the_survivor(
    rail: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    """DEC-263: a merge leaves workspace rows where they are; the survivor's reads follow
    merged_into_id at any depth, each workspace seeing only its own."""
    as_, ids = rail
    with Session(db_engine) as session:
        older = Product(name="Merged earlier", merged_into_id=ids["merged"])  # two hops
        session.add(older)
        session.flush()
        workspace = {
            key: session.scalars(
                select(Workspace.id).where(Workspace.name == f"Workspace {key}")
            ).one()
            for key in "ab"
        }
        author = session.scalars(select(User.id).where(User.clerk_user_id == "user_a")).one()
        session.add_all(
            [
                ProductNote(
                    workspace_id=workspace["a"],
                    product_id=older.id,
                    author_id=author,
                    body="noted before the merge",
                ),
                ProductTag(workspace_id=workspace["a"], product_id=ids["merged"], tag="Winner"),
                ProductTag(workspace_id=workspace["a"], product_id=older.id, tag="winner"),
                ProductTag(workspace_id=workspace["a"], product_id=ids["product"], tag="Q4"),
                ProductTag(workspace_id=workspace["b"], product_id=ids["merged"], tag="theirs"),
            ]
        )
        session.commit()
        older_id = older.id
    notes = f"/v1/products/{ids['product']}/notes"
    tags = f"/v1/products/{ids['product']}/tags"
    a = as_("a")
    assert [note["body"] for note in a.get(notes).json()["items"]] == ["noted before the merge"]
    assert a.get(tags).json() == {"tags": ["Q4", "Winner"]}  # one per case-insensitive spelling
    assert as_("b").get(tags).json() == {"tags": ["theirs"]}
    assert as_("b").get(notes).json()["items"] == []

    # A PUT replaces the whole group's tags, so a removed tag never comes back from a merged id.
    assert as_("a").put(tags, json={"tags": ["Q4"]}).json() == {"tags": ["Q4"]}
    with Session(db_engine) as session:
        rows = session.execute(select(ProductTag.product_id, ProductTag.tag)).tuples().all()
        assert sorted(rows, key=str) == sorted(
            [(ids["product"], "Q4"), (ids["merged"], "theirs")], key=str
        )
        assert session.scalars(select(ProductNote.product_id)).all() == [older_id]  # never moved
