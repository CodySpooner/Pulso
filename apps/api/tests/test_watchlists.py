from collections.abc import Callable, Iterator
from datetime import datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import Image, Listing, Product, User, WatchlistItem, Workspace

# Watchlists (WF-2 part a, DEC-314): workspace-owned lists of global products.

As = Callable[[str], TestClient]


@pytest.fixture
def lists(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, UUID]]:
    """`as_("a")` makes the next requests workspace A's. ids: p0..p5, and "merged", which was
    merged into "middle", which was merged into p0."""
    with Session(db_engine) as session:
        users = {key: User(clerk_user_id=f"user_{key}") for key in "ab"}
        workspaces = {key: Workspace(name=f"Workspace {key}") for key in "ab"}
        products = {f"p{i}": Product(name=f"Product {i}") for i in range(6)}
        session.add_all([*users.values(), *workspaces.values(), *products.values()])
        session.flush()
        products["middle"] = Product(name="Middle", merged_into_id=products["p0"].id)
        session.add(products["middle"])
        session.flush()
        products["merged"] = Product(name="Merged", merged_into_id=products["middle"].id)
        listing = Listing(source_id=1, external_id="1", url="https://s.example.test", title="x")
        session.add_all([products["merged"], listing])
        session.flush()
        image = Image(listing_id=listing.id, url="https://cdn.example.test/p1.jpg", position=0)
        session.add(image)
        session.flush()
        products["p1"].main_image_id = image.id
        session.commit()
        principals = {key: Principal(users[key].id, workspaces[key].id) for key in "ab"}
        ids = {key: product.id for key, product in products.items()}
        ids |= {f"workspace_{key}": workspace.id for key, workspace in workspaces.items()}

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


def items(client: TestClient, list_id: str) -> list[str]:
    page = client.get(f"/v1/watchlists/{list_id}/items").json()
    return [item["product_id"] for item in page["items"]]


def added(client: TestClient, list_id: str) -> dict[str, str]:
    page = client.get(f"/v1/watchlists/{list_id}/items").json()
    return {item["product_id"]: item["added_at"] for item in page["items"]}


@pytest.mark.db
def test_first_star_creates_main_and_a_second_is_a_noop(
    lists: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = lists
    client = as_("a")
    assert client.get("/v1/watchlists").json() == []
    first = client.put(f"/v1/products/{ids['p1']}/watch")
    assert first.status_code == 200
    [main] = client.get("/v1/watchlists").json()
    assert (main["name"], main["position"], main["item_count"]) == ("Main", 0, 1)
    assert first.json() == {
        "watchlist_id": main["id"],
        "product_id": str(ids["p1"]),
        "added_at": first.json()["added_at"],
    }
    again = client.put(f"/v1/products/{ids['p1']}/watch")
    assert again.json() == first.json()  # added_at kept
    assert client.get("/v1/watchlists").json() == [main]
    page = client.get(f"/v1/watchlists/{main['id']}/items").json()
    [row] = page["items"]
    assert page["next_cursor"] is None
    assert {key: row[key] for key in ("product_id", "name", "image_url", "added_at")} == {
        "product_id": str(ids["p1"]),
        "name": "Product 1",
        "image_url": "https://cdn.example.test/p1.jpg",
        "added_at": first.json()["added_at"],
    }
    # The product as Discover reads it, starred (DEC-322).
    assert (row["product"]["id"], row["product"]["title"]) == (str(ids["p1"]), "Product 1")
    assert (row["product"]["watched"], row["product"]["watchlist_ids"]) == (True, [main["id"]])

    # A merged product stars its survivor, through a chain of merges.
    merged = client.put(f"/v1/products/{ids['merged']}/watch").json()
    assert merged["product_id"] == str(ids["p0"])
    assert client.put(f"/v1/products/{uuid4()}/watch").status_code == 404

    # Unstar: off Main, and again is a no-op (null).
    removed = client.delete(f"/v1/products/{ids['p1']}/watch")
    assert (removed.status_code, removed.json()) == (200, first.json())
    assert client.delete(f"/v1/products/{ids['p1']}/watch").json() is None
    assert items(client, main["id"]) == [str(ids["p0"])]
    # Merged after its star: unstarring the survivor takes the stored product off.
    client.put(f"/v1/products/{ids['p3']}/watch")
    with Session(db_engine) as session:
        session.get_one(Product, ids["p3"]).merged_into_id = ids["p4"]
        session.commit()
    assert client.delete(f"/v1/products/{ids['p4']}/watch").json()["product_id"] == str(ids["p3"])

    # Main, deleted, comes back with the next star, placed last.
    client.post("/v1/watchlists", json={"name": "Pet niche"})
    assert client.delete(f"/v1/watchlists/{main['id']}").status_code == 200
    reborn = client.put(f"/v1/products/{ids['p2']}/watch").json()["watchlist_id"]
    assert [(w["id"] == reborn, w["name"]) for w in client.get("/v1/watchlists").json()] == [
        (False, "Pet niche"),
        (True, "Main"),
    ]


@pytest.mark.db
def test_lists_are_created_renamed_reordered_and_deleted(
    lists: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = lists
    client = as_("a")
    created = [client.post("/v1/watchlists", json={"name": n}) for n in ("Q4", " Pet ", "Gym")]
    assert [r.status_code for r in created] == [201] * 3
    q4, pet, gym = (r.json()["id"] for r in created)
    assert [(w["name"], w["position"]) for w in client.get("/v1/watchlists").json()] == [
        ("Q4", 0),
        ("Pet", 1),
        ("Gym", 2),
    ]
    duplicate = client.post("/v1/watchlists", json={"name": "Q4"})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "conflict")
    for body in ({"name": "  "}, {"name": "x" * 81}, {"name": "x", "color": "red"}, {}):
        assert client.post("/v1/watchlists", json=body).status_code == 422, body
    assert client.patch(f"/v1/watchlists/{pet}", json={"name": "Gym"}).status_code == 409
    assert client.patch(f"/v1/watchlists/{pet}", json={"position": -1}).status_code == 422

    renamed = client.patch(f"/v1/watchlists/{pet}", json={"name": "Pets", "position": 0})
    assert (renamed.json()["name"], renamed.json()["position"]) == ("Pets", 0)
    assert client.patch(f"/v1/watchlists/{q4}", json={"position": 99}).json()["position"] == 2
    order = [(w["name"], w["position"]) for w in client.get("/v1/watchlists").json()]
    assert order == [("Pets", 0), ("Gym", 1), ("Q4", 2)]

    client.post(f"/v1/watchlists/{gym}/items", json={"product_ids": [str(ids["p1"])]})
    deleted = client.delete(f"/v1/watchlists/{gym}")
    assert (deleted.json()["name"], deleted.json()["item_count"]) == ("Gym", 1)
    assert client.delete(f"/v1/watchlists/{gym}").status_code == 404
    assert [w["name"] for w in client.get("/v1/watchlists").json()] == ["Pets", "Q4"]
    with Session(db_engine) as session:  # the items went with the list
        assert session.scalar(select(func.count()).select_from(WatchlistItem)) == 0


@pytest.mark.db
def test_items_add_move_and_remove(lists: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = lists
    client = as_("a")
    a = client.post("/v1/watchlists", json={"name": "A"}).json()["id"]
    b = client.post("/v1/watchlists", json={"name": "B"}).json()["id"]
    add = {"product_ids": [str(ids[k]) for k in ("p1", "p2", "merged", "p0")]}
    response = client.post(f"/v1/watchlists/{a}/items", json=add)
    assert (response.status_code, response.json()["item_count"]) == (200, 3)  # merged is p0
    first = added(client, a)
    assert set(first) == {str(ids[k]) for k in ("p0", "p1", "p2")}
    again = client.post(f"/v1/watchlists/{a}/items", json={"product_ids": [str(ids["p1"])]})
    assert again.json()["item_count"] == 3
    assert added(client, a) == first
    unknown = {"product_ids": [str(ids["p3"]), str(uuid4())]}
    assert client.post(f"/v1/watchlists/{a}/items", json=unknown).status_code == 404
    assert client.post(f"/v1/watchlists/{a}/items", json={"product_ids": []}).status_code == 422
    assert len(items(client, a)) == 3

    # B already holds p1, added later: the move keeps A's earlier added_at.
    client.post(f"/v1/watchlists/{b}/items", json={"product_ids": [str(ids["p1"])]})
    move = {"product_ids": [str(ids["p1"]), str(ids["p2"]), str(ids["p5"])], "to": b}
    moved = client.post(f"/v1/watchlists/{a}/items/move", json=move)
    assert (moved.json()["id"], moved.json()["item_count"]) == (b, 2)  # p5 wasn't on A
    assert items(client, a) == [str(ids["p0"])]
    assert added(client, b) == {str(ids[k]): first[str(ids[k])] for k in ("p1", "p2")}
    same = {"product_ids": [str(ids["p0"])], "to": a}
    assert client.post(f"/v1/watchlists/{a}/items/move", json=same).json()["item_count"] == 1

    removed = client.delete(f"/v1/watchlists/{b}/items/{ids['p1']}")
    assert removed.json()["item_count"] == 1
    assert client.delete(f"/v1/watchlists/{b}/items/{ids['p1']}").json()["item_count"] == 1
    assert items(client, b) == [str(ids["p2"])]


@pytest.mark.db
def test_items_page_newest_first_and_stable(lists: tuple[As, dict[str, UUID]]) -> None:
    as_, ids = lists
    client = as_("a")
    a = client.post("/v1/watchlists", json={"name": "A"}).json()["id"]
    url = f"/v1/watchlists/{a}/items"
    client.post(url, json={"product_ids": [str(ids["p1"])]})
    # One request: one added_at, so product_id breaks the tie.
    client.post(url, json={"product_ids": [str(ids[f"p{i}"]) for i in (2, 3, 4)]})
    client.post(url, json={"product_ids": [str(ids["p5"])]})
    full = client.get(url).json()["items"]
    keys = [(datetime.fromisoformat(i["added_at"]), UUID(i["product_id"])) for i in full]
    assert keys == sorted(keys, reverse=True) and keys[0][1] == ids["p5"]
    page = client.get(url, params={"limit": 2}).json()
    seen = page["items"]
    while page["next_cursor"] is not None:
        page = client.get(url, params={"limit": 2, "cursor": page["next_cursor"]}).json()
        seen += page["items"]
    assert seen == full
    response = client.get(url, params={"cursor": "not-json"})
    assert (response.status_code, response.json()["code"]) == (422, "invalid_cursor")
    assert client.get(url, params={"limit": 101}).status_code == 422


@pytest.mark.db
def test_workspace_b_never_sees_or_edits_a(
    lists: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = lists
    a_main = as_("a").put(f"/v1/products/{ids['p1']}/watch").json()["watchlist_id"]
    a_lists = as_("a").get("/v1/watchlists").json()
    b = as_("b")
    assert b.get("/v1/watchlists").json() == []
    mine = b.post("/v1/watchlists", json={"name": "Main"}).json()["id"]  # A's name is free
    one = {"product_ids": [str(ids["p2"])]}
    for response in (
        b.get(f"/v1/watchlists/{a_main}/items"),
        b.patch(f"/v1/watchlists/{a_main}", json={"name": "Mine"}),
        b.delete(f"/v1/watchlists/{a_main}"),
        b.post(f"/v1/watchlists/{a_main}/items", json=one),
        b.delete(f"/v1/watchlists/{a_main}/items/{ids['p1']}"),
        b.post(f"/v1/watchlists/{a_main}/items/move", json=one | {"to": mine}),
        b.post(f"/v1/watchlists/{mine}/items/move", json=one | {"to": a_main}),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    # B's star lands on B's own Main; unstarring never reaches A's.
    assert b.put(f"/v1/products/{ids['p1']}/watch").json()["watchlist_id"] == mine
    assert b.delete(f"/v1/products/{ids['p1']}/watch").json()["watchlist_id"] == mine
    assert b.delete(f"/v1/products/{ids['p1']}/watch").json() is None
    assert as_("a").get("/v1/watchlists").json() == a_lists
    assert items(as_("a"), a_main) == [str(ids["p1"])]

    # The database refuses an item in another workspace's list.
    with Session(db_engine) as session, pytest.raises(IntegrityError):
        session.add(
            WatchlistItem(
                workspace_id=ids["workspace_b"], watchlist_id=UUID(a_main), product_id=ids["p3"]
            )
        )
        session.commit()


def statements(db_engine: Engine, request: Callable[[], object]) -> int:
    """How many SQL statements `request` runs."""
    count = 0

    def capture(*_: object) -> None:
        nonlocal count
        count += 1

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        request()
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
    return count


@pytest.mark.db
def test_star_state_reads_on_the_product_page_and_discover_rows(
    lists: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    """DEC-322: `watched` is on Main, `watchlist_ids` every list holding the product, or a
    product merged into it, from one query per page whatever its size; workspace scoped."""
    as_, ids = lists
    with Session(db_engine) as session:
        session.add_all(Product(name=f"Filler {i}") for i in range(50))
        session.commit()
    a = as_("a")
    main = a.put(f"/v1/products/{ids['p1']}/watch").json()["watchlist_id"]
    pet = a.post("/v1/watchlists", json={"name": "Pet"}).json()["id"]
    a.post(f"/v1/watchlists/{pet}/items", json={"product_ids": [str(ids["p1"]), str(ids["p2"])]})
    a.put(f"/v1/products/{ids['p3']}/watch")
    with Session(db_engine) as session:  # merged after its star: the survivor reads starred
        session.get_one(Product, ids["p3"]).merged_into_id = ids["p4"]
        session.commit()

    def state(client: TestClient, key: str) -> tuple[bool, list[str]]:
        body = client.get(f"/v1/products/{ids[key]}").json()
        return body["watched"], body["watchlist_ids"]

    assert state(a, "p1") == (True, [main, pet])
    assert state(a, "p2") == (False, [pet])  # on a list, but not starred
    assert state(a, "p4") == (True, [main])
    assert state(a, "p5") == (False, [])
    feed = {row["id"]: row for row in a.get("/v1/products", params={"limit": 100}).json()["items"]}
    assert len(feed) == 55  # p0..p2, p4, p5 and the fillers
    for key in ("p1", "p2", "p4", "p5"):
        assert (feed[str(ids[key])]["watched"], feed[str(ids[key])]["watchlist_ids"]) == state(
            a, key
        )
    # B's reads never see A's lists.
    b = as_("b")
    assert state(b, "p1") == (False, [])
    b_feed = b.get("/v1/products", params={"limit": 100}).json()["items"]
    assert {(row["watched"], tuple(row["watchlist_ids"])) for row in b_feed} == {(False, ())}

    # No query per row: a 50-row page runs as many statements as a 1-row page.
    one = statements(db_engine, lambda: a.get("/v1/products", params={"limit": 1}))
    fifty = statements(db_engine, lambda: a.get("/v1/products", params={"limit": 50}))
    assert fifty == one


@pytest.mark.db
def test_items_read_the_product_now_and_a_merged_one_as_its_survivor(
    lists: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = lists
    with Session(db_engine) as session:
        fillers = [Product(name=f"Filler {i}") for i in range(50)]
        session.add_all(fillers)
        session.commit()
        filler_ids = [str(product.id) for product in fillers]
    a = as_("a")
    pet = a.post("/v1/watchlists", json={"name": "Pet"}).json()["id"]
    url = f"/v1/watchlists/{pet}/items"
    a.post(url, json={"product_ids": [str(ids["p2"]), str(ids["p3"])]})
    with Session(db_engine) as session:  # p3 merged after the add: the item isn't rewritten
        session.get_one(Product, ids["p3"]).merged_into_id = ids["p4"]
        session.commit()
    rows = {row["product_id"]: row for row in a.get(url).json()["items"]}
    merged = rows[str(ids["p3"])]
    assert (merged["name"], merged["product"]["id"]) == ("Product 3", str(ids["p4"]))
    assert merged["product"]["title"] == "Product 4"
    assert merged["product"]["watchlist_ids"] == [pet]  # through p3
    assert rows[str(ids["p2"])]["product"]["id"] == str(ids["p2"])
    for stat in ("store_count", "price_min_minor"):  # nothing collected: no source yet, never 0
        assert rows[str(ids["p2"])]["product"][stat]["value"] is None

    # No query per item either.
    a.post(url, json={"product_ids": filler_ids})
    one = statements(db_engine, lambda: a.get(url, params={"limit": 1}))
    fifty = statements(db_engine, lambda: a.get(url, params={"limit": 50}))
    assert fifty == one
