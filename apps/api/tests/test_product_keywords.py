from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import Listing, Product, ProductKeyword, User, Workspace

# KW-1 (DEC-281): candidates from the product's titles on read; the workspace's confirm, reject
# and typed-in keywords as rows that a new decision updates and nothing deletes.

As = Callable[[str], TestClient]
SEEN = datetime(2026, 10, 24, 6, 0, tzinfo=UTC)
TITLES = [
    "Sunset Projection Lamp, 16 Colors, USB",
    "LED Sunset Lamp Projector for Bedroom",
    "Sunset Projection Lamp – Rainbow Night Light",
]


@pytest.fixture
def rail(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, UUID]]:
    """`as_("a")` makes the next requests workspace A's; ids holds the products."""
    with Session(db_engine) as session:
        users = {k: User(clerk_user_id=f"user_{k}") for k in "ab"}
        workspaces = {k: Workspace(name=f"Workspace {k}") for k in "ab"}
        survivor = Product(name="Sunset projection lamp with 16 colour modes and remote")
        session.add_all([*users.values(), *workspaces.values(), survivor])
        session.flush()
        merged = Product(name="Sunset lamp", merged_into_id=survivor.id)
        session.add(merged)
        session.add_all(
            Listing(
                source_id=1,
                external_id=f"l{i}",
                url=f"https://store{i}.example.test/p",
                title=title,
                product_id=survivor.id,
                last_seen_at=SEEN.replace(hour=i),
            )
            for i, title in enumerate(TITLES)
        )
        session.commit()
        principals = {k: Principal(users[k].id, workspaces[k].id) for k in "ab"}
        ids = {"product": survivor.id, "merged": merged.id, "user_a": users["a"].id}
        ids |= {f"workspace_{k}": workspaces[k].id for k in "ab"}

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


def by_status(body: dict[str, Any], status: str) -> list[str]:
    return [k["keyword"] for k in body["keywords"] if k["status"] == status]


def url(ids: dict[str, UUID], product: str = "product") -> str:
    return f"/v1/products/{ids[product]}/keywords"


@pytest.mark.db
def test_candidates_come_from_the_name_and_listing_titles(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    response = as_("a").get(url(ids))
    assert response.status_code == 200
    keywords = response.json()["keywords"]
    assert keywords[0] == {
        "keyword": "sunset projection lamp",
        "relevance": 0.833,  # in 3 of 4 titles, its words in 4, 3 and 4
        "as_of": "2026-10-24T02:00:00Z",  # the newest title Pulso read
        "source": "title",
        "status": "candidate",
        "decided_at": None,
    }
    assert {k["status"] for k in keywords} == {"candidate"}
    assert "with" not in {w for k in keywords for w in k["keyword"].split()}
    assert len(keywords) <= 12


@pytest.mark.db
def test_confirm_reject_and_add_round_trip_with_who_and_when(
    rail: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = rail
    client = as_("a")
    confirmed = client.post(
        url(ids), json={"keyword": "sunset projection lamp", "status": "confirmed"}
    )
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert by_status(body, "confirmed") == ["sunset projection lamp"]
    assert "sunset projection lamp" not in by_status(body, "candidate")
    row = body["keywords"][0]
    assert (row["source"], row["relevance"], row["decided_at"] is not None) == (
        "title",
        0.833,
        True,
    )
    assert client.get(url(ids)).json() == body

    rejected = client.post(url(ids), json={"keyword": "Sunset", "status": "rejected"}).json()
    assert by_status(rejected, "rejected") == ["sunset"]
    # Typed in: normalized, and no title holds it, so no relevance.
    added = client.post(
        url(ids), json={"keyword": "  Sunset Lamp for   BEDROOM ", "status": "confirmed"}
    )
    mine = next(k for k in added.json()["keywords"] if k["keyword"] == "sunset lamp for bedroom")
    assert (mine["source"], mine["status"], mine["relevance"]) == ("manual", "confirmed", None)

    # Changing a decision updates the same row; nothing is deleted.
    with Session(db_engine) as session:
        before = session.scalars(
            select(ProductKeyword.decided_at).where(ProductKeyword.keyword == "sunset")
        ).one()
    again = client.post(url(ids), json={"keyword": "sunset", "status": "confirmed"}).json()
    assert "sunset" in by_status(again, "confirmed")
    # A repeat of the same decision changes nothing, so decided_at keeps its first time.
    client.post(url(ids), json={"keyword": "sunset projection lamp", "status": "confirmed"})
    with Session(db_engine) as session:
        rows = {
            r.keyword: r
            for r in session.scalars(select(ProductKeyword).order_by(ProductKeyword.keyword))
        }
        assert sorted(rows) == ["sunset", "sunset lamp for bedroom", "sunset projection lamp"]
        assert rows["sunset"].status == "confirmed" and rows["sunset"].decided_at > before
        assert rows["sunset projection lamp"].relevance is not None
        assert rows["sunset projection lamp"].decided_at < rows["sunset"].decided_at
        assert {r.decided_by for r in rows.values()} == {ids["user_a"]}
        assert {r.workspace_id for r in rows.values()} == {ids["workspace_a"]}


@pytest.mark.db
def test_a_plural_or_case_variant_decides_the_same_keyword(
    rail: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = rail
    client = as_("a")
    client.post(url(ids), json={"keyword": "sunset projection lamp", "status": "confirmed"})
    body = client.post(url(ids), json={"keyword": "Sunset Projection LAMPS", "status": "rejected"})
    assert by_status(body.json(), "rejected") == ["sunset projection lamp"]
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductKeyword)) == 1


@pytest.mark.db
def test_bad_input_unknown_and_merged_products(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    client = as_("a")
    for body in (
        {"keyword": "   ", "status": "confirmed"},
        {"keyword": "!!! ---", "status": "confirmed"},
        {"keyword": "x" * 101, "status": "confirmed"},
        {"keyword": "lamp", "status": "candidate"},
        {"keyword": "lamp", "status": "confirmed", "source": "title"},
        {"keyword": "lamp"},
    ):
        assert client.post(url(ids), json=body).status_code == 422, body
    unknown = f"/v1/products/{uuid4()}/keywords"
    assert client.get(unknown).status_code == 404
    assert client.post(unknown, json={"keyword": "lamp", "status": "confirmed"}).status_code == 404
    merged = client.post(url(ids, "merged"), json={"keyword": "lamp", "status": "confirmed"})
    assert (merged.status_code, merged.json()["code"]) == (409, "merged")


@pytest.mark.db
def test_workspace_b_never_sees_or_changes_a_s_keywords(rail: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = rail
    as_("a").post(url(ids), json={"keyword": "sunset projection lamp", "status": "confirmed"})
    as_("a").post(url(ids), json={"keyword": "galaxy lamp", "status": "confirmed"})

    b = as_("b").get(url(ids)).json()
    assert by_status(b, "confirmed") == [] and by_status(b, "rejected") == []
    assert "sunset projection lamp" in by_status(b, "candidate")  # still undecided for B
    as_("b").post(url(ids), json={"keyword": "sunset projection lamp", "status": "rejected"})

    a = as_("a").get(url(ids)).json()
    assert by_status(a, "confirmed") == ["sunset projection lamp", "galaxy lamp"]
    assert by_status(as_("b").get(url(ids)).json(), "rejected") == ["sunset projection lamp"]


@pytest.mark.db
def test_decisions_on_a_merged_product_read_through_the_survivor(
    rail: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    """As notes and tags (DEC-263): a merge leaves the rows; the survivor reads them, and the
    newest decision on a keyword wins."""
    as_, ids = rail
    with Session(db_engine) as session:
        session.add_all(
            ProductKeyword(
                workspace_id=ids["workspace_a"],
                product_id=ids["merged"],
                keyword=keyword,
                source="manual",
                status=status,
                decided_by=ids["user_a"],
            )
            for keyword, status in (("sunset lamp", "confirmed"), ("lamp", "rejected"))
        )
        session.commit()
    body = as_("a").get(url(ids)).json()
    assert by_status(body, "confirmed") == ["sunset lamp"]
    assert "lamp" in by_status(body, "rejected") and "lamp" not in by_status(body, "candidate")
    assert by_status(as_("b").get(url(ids)).json(), "confirmed") == []

    after = as_("a").post(url(ids), json={"keyword": "sunset lamps", "status": "rejected"}).json()
    assert "sunset lamp" in by_status(after, "rejected")  # the survivor's newer row wins
    with Session(db_engine) as session:
        rows = session.execute(
            select(ProductKeyword.product_id, ProductKeyword.status).where(
                ProductKeyword.keyword == "sunset lamp"
            )
        ).all()
        assert sorted(rows, key=str) == sorted(
            [(ids["merged"], "confirmed"), (ids["product"], "rejected")], key=str
        )
