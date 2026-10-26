import csv
import io
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.csv_export import major
from pulso_api.dependencies import get_db
from pulso_api.routers.boards import BOARD_CSV
from pulso_api.routers.product_scores import NO_ROW
from pulso_api.routers.products import NO_PRICE, NO_SETTINGS
from pulso_core.models import (
    BoardItem,
    CollectorRun,
    Image,
    Listing,
    ListingSnapshot,
    Product,
    ProductTest,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    User,
    Workspace,
    WorkspaceSettings,
)
from pulso_core.scores import Explanation, ScoreRow, write

# Boards (WF-3 part a, DEC-319): workspace boards of global products, ordered and noted.
# Card stats (imp-454): each card's price range, best margin and scores, a page in a fixed
# number of queries. CSV (imp-456): the cards as the JSON builds them.

As = Callable[[str], TestClient]
DAY = datetime.now(UTC).date() - timedelta(days=1)  # scored yesterday
AT = datetime.combine(DAY, datetime.min.time(), UTC) + timedelta(hours=6)
FEES = {"payment_fee_bps": 290, "payment_fee_fixed_minor": 30, "returns_bps": 500}


@pytest.fixture
def boards(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, UUID]]:
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


def add(client: TestClient, board: str, ids: dict[str, UUID], *keys: str) -> dict[str, list[str]]:
    body = {"product_ids": [str(ids[key]) for key in keys]}
    response = client.post(f"/v1/boards/{board}/items", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, list[str]] = response.json()
    return result


def cards(client: TestClient, board: str) -> list[tuple[str, int]]:
    page = client.get(f"/v1/boards/{board}/items").json()
    return [(item["product_id"], item["position"]) for item in page["items"]]


@pytest.mark.db
def test_boards_are_created_edited_archived_and_deleted(
    boards: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = boards
    client = as_("a")
    assert client.get("/v1/boards").json() == []
    created = client.post("/v1/boards", json={"name": " Q4 gifts ", "description": "For Nov"})
    assert created.status_code == 201
    q4 = created.json()
    assert (q4["name"], q4["description"], q4["archived_at"], q4["item_count"]) == (
        "Q4 gifts",
        "For Nov",
        None,
        0,
    )
    pet = client.post("/v1/boards", json={"name": "Pet niche"}).json()
    assert pet["description"] is None
    duplicate = client.post("/v1/boards", json={"name": "Q4 gifts"})
    assert (duplicate.status_code, duplicate.json()["code"]) == (409, "conflict")
    for body in ({"name": "  "}, {"name": "x" * 81}, {"name": "x", "color": "red"}, {}):
        assert client.post("/v1/boards", json=body).status_code == 422, body
    assert client.patch(f"/v1/boards/{pet['id']}", json={"name": "Q4 gifts"}).status_code == 409

    # Newest activity first: the PATCH puts Q4 back on top.
    assert [b["name"] for b in client.get("/v1/boards").json()] == ["Pet niche", "Q4 gifts"]
    edited = client.patch(f"/v1/boards/{q4['id']}", json={"name": "Q4", "description": None})
    assert (edited.json()["name"], edited.json()["description"]) == ("Q4", None)
    assert datetime.fromisoformat(edited.json()["updated_at"]) > datetime.fromisoformat(
        q4["updated_at"]
    )
    assert client.patch(f"/v1/boards/{q4['id']}", json={}).json()["name"] == "Q4"
    assert [b["name"] for b in client.get("/v1/boards").json()] == ["Q4", "Pet niche"]

    # Archive hides the board from the default list; again keeps the first archived_at.
    archived = client.post(f"/v1/boards/{pet['id']}/archive").json()
    assert archived["archived_at"] is not None
    again = client.post(f"/v1/boards/{pet['id']}/archive").json()
    assert again["archived_at"] == archived["archived_at"]
    assert [b["name"] for b in client.get("/v1/boards").json()] == ["Q4"]
    shelved = client.get("/v1/boards", params={"archived": True}).json()
    assert [b["name"] for b in shelved] == ["Pet niche"]
    assert client.post("/v1/boards", json={"name": "Pet niche"}).status_code == 409
    assert client.post(f"/v1/boards/{pet['id']}/unarchive").json()["archived_at"] is None
    assert client.get("/v1/boards", params={"archived": True}).json() == []

    # Delete returns the board as it was, and its cards go with it.
    add(client, q4["id"], ids, "p1", "p2")
    deleted = client.delete(f"/v1/boards/{q4['id']}")
    assert (deleted.json()["name"], deleted.json()["item_count"]) == ("Q4", 2)
    assert client.delete(f"/v1/boards/{q4['id']}").status_code == 404
    assert [b["name"] for b in client.get("/v1/boards").json()] == ["Pet niche"]
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(BoardItem)) == 0


@pytest.mark.db
def test_cards_append_move_take_notes_and_go(
    boards: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = boards
    client = as_("a")
    board = client.post("/v1/boards", json={"name": "A"}).json()["id"]
    first = add(client, board, ids, "p1", "p2", "merged", "p0")  # merged is p0
    assert first == {"added": [str(ids[k]) for k in ("p1", "p2", "p0")], "skipped": []}
    again = add(client, board, ids, "p3", "p1", "middle")  # middle is p0 too
    assert again == {"added": [str(ids["p3"])], "skipped": [str(ids["p1"]), str(ids["p0"])]}
    order = [str(ids[k]) for k in ("p1", "p2", "p0", "p3")]
    assert cards(client, board) == list(zip(order, range(4), strict=True))
    unknown = {"product_ids": [str(ids["p4"]), str(uuid4())]}
    assert client.post(f"/v1/boards/{board}/items", json=unknown).status_code == 404
    assert client.post(f"/v1/boards/{board}/items", json={"product_ids": []}).status_code == 422
    page = client.get(f"/v1/boards/{board}/items").json()
    assert page["items"][0] == {
        "product_id": str(ids["p1"]),
        "name": "Product 1",
        "image_url": "https://cdn.example.test/p1.jpg",
        "position": 0,
        "note": None,
        "added_at": page["items"][0]["added_at"],
        # imp-454: nothing backs p1's stats, so each is null with its reason, never 0 (DEC-040).
        "merged_into_id": None,
        "currency": "USD",
        "price_min_minor": {"value": None, "reason": NO_PRICE},
        "price_max_minor": {"value": None, "reason": NO_PRICE},
        "best_margin_minor": {"value": None, "reason": NO_SETTINGS, "missing": []},
        "trend": {"value": None, "reason": NO_ROW},
        "saturation": {"value": None, "reason": NO_ROW},
        "lifecycle": {"value": None, "reason": NO_ROW},
    }

    # A note round-trips, survives a move, and null clears it.
    url = f"/v1/boards/{board}/items/{ids['p2']}"
    noted = client.patch(url, json={"note": "  Bundle with p3  "}).json()
    assert (noted["note"], noted["position"]) == ("Bundle with p3", 1)
    assert client.patch(url, json={"position": 3}).json()["note"] == "Bundle with p3"
    order = [str(ids[k]) for k in ("p1", "p0", "p3", "p2")]
    assert cards(client, board) == list(zip(order, range(4), strict=True))
    assert client.patch(url, json={"note": None}).json()["note"] is None
    assert client.patch(url, json={"position": -1}).status_code == 422
    assert client.patch(url, json={"note": "b\x00d"}).status_code == 422

    # Removing leaves a gap; the next move renumbers 0..n-1, past the end is last.
    removed = client.delete(f"/v1/boards/{board}/items/{ids['p0']}")
    assert removed.json()["item_count"] == 3
    assert client.delete(f"/v1/boards/{board}/items/{ids['p0']}").json()["item_count"] == 3
    moved = client.patch(f"/v1/boards/{board}/items/{ids['p1']}", json={"position": 99})
    assert moved.json()["position"] == 2
    between = client.patch(f"/v1/boards/{board}/items/{ids['p1']}", json={"position": 1})
    assert between.json()["position"] == 1
    order = [str(ids[k]) for k in ("p3", "p1", "p2")]
    with Session(db_engine) as fresh:  # persisted, read back outside the API
        stored = fresh.execute(
            select(BoardItem.product_id, BoardItem.position)
            .where(BoardItem.board_id == UUID(board))
            .order_by(BoardItem.position)
        ).all()
    assert [(str(p), n) for p, n in stored] == list(zip(order, range(3), strict=True))
    missing = client.patch(f"/v1/boards/{board}/items/{ids['p0']}", json={"note": "x"})
    assert missing.status_code == 404


@pytest.mark.db
def test_items_page_in_board_order_and_every_write_bumps_the_board(
    boards: tuple[As, dict[str, UUID]],
) -> None:
    as_, ids = boards
    client = as_("a")
    a = client.post("/v1/boards", json={"name": "A"}).json()
    b = client.post("/v1/boards", json={"name": "B"}).json()
    add(client, a["id"], ids, *(f"p{i}" for i in range(6)))
    url = f"/v1/boards/{a['id']}/items"
    full = client.get(url).json()["items"]
    page = client.get(url, params={"limit": 4}).json()
    seen = page["items"]
    while page["next_cursor"] is not None:
        page = client.get(url, params={"limit": 4, "cursor": page["next_cursor"]}).json()
        seen += page["items"]
    assert seen == full and [item["position"] for item in full] == list(range(6))
    response = client.get(url, params={"cursor": "not-json"})
    assert (response.status_code, response.json()["code"]) == (422, "invalid_cursor")
    assert client.get(url, params={"limit": 101}).status_code == 422

    def top() -> str:  # the most recently written board, archived or not
        every = client.get("/v1/boards").json()
        every += client.get("/v1/boards", params={"archived": True}).json()
        return str(max(every, key=lambda board: datetime.fromisoformat(board["updated_at"]))["id"])

    for method, path, body in (
        ("POST", "/items", {"product_ids": [str(ids["p1"])]}),  # skipped, still a write
        ("PATCH", f"/items/{ids['p1']}", {"note": "x"}),
        ("DELETE", f"/items/{ids['p5']}", None),
        ("POST", "/archive", None),
        ("POST", "/unarchive", None),
        ("POST", "/items/send-to-testing", {"product_ids": [str(ids["p4"])]}),
    ):
        client.patch(f"/v1/boards/{b['id']}", json={})  # B on top
        assert top() == b["id"]
        assert client.request(method, f"/v1/boards/{a['id']}{path}", json=body).status_code == 200
        assert top() == a["id"], path


@pytest.mark.db
def test_send_to_testing_opens_idea_tests_and_skips_open_ones(
    boards: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = boards
    client = as_("a")
    with Session(db_engine) as session:  # p1 has an open test; p2's ended as a winner
        session.add_all(
            [
                ProductTest(workspace_id=ids["workspace_a"], product_id=ids["p1"], stage="idea"),
                ProductTest(workspace_id=ids["workspace_a"], product_id=ids["p2"], stage="winner"),
                ProductTest(workspace_id=ids["workspace_b"], product_id=ids["p0"], stage="idea"),
            ]
        )
        session.commit()
    board = client.post("/v1/boards", json={"name": "A"}).json()["id"]
    add(client, board, ids, "p1", "p2", "p0")
    send = {"product_ids": [str(ids[k]) for k in ("p1", "p2", "merged")]}  # merged is p0
    sent = client.post(f"/v1/boards/{board}/items/send-to-testing", json=send)
    assert sent.status_code == 200, sent.text
    created = sent.json()["created"]
    assert [(t["product_id"], t["stage"]) for t in created] == [
        (str(ids["p2"]), "idea"),
        (str(ids["p0"]), "idea"),
    ]
    assert all(t["start_snapshot"] is None and t["cpa_minor"] is None for t in created)
    assert sent.json()["skipped"] == [str(ids["p1"])]
    listed = client.get("/v1/tests", params={"stage": "idea"}).json()["items"]
    assert {t["product_id"] for t in listed} == {str(ids[k]) for k in ("p0", "p1", "p2")}
    # Sent again, all three are open now.
    resent = client.post(f"/v1/boards/{board}/items/send-to-testing", json=send).json()
    assert resent == {"created": [], "skipped": [str(ids[k]) for k in ("p1", "p2", "p0")]}
    unknown = {"product_ids": [str(uuid4())]}
    assert client.post(f"/v1/boards/{board}/items/send-to-testing", json=unknown).status_code == 404
    with Session(db_engine) as session:  # B's own open test on p0 was neither seen nor touched
        b_tests = select(func.count()).where(ProductTest.workspace_id == ids["workspace_b"])
        assert session.scalar(b_tests) == 1


@pytest.mark.db
def test_workspace_b_never_sees_or_edits_a(
    boards: tuple[As, dict[str, UUID]], db_engine: Engine
) -> None:
    as_, ids = boards
    a = as_("a").post("/v1/boards", json={"name": "Mine"}).json()["id"]
    add(as_("a"), a, ids, "p1")
    as_("a").patch(f"/v1/boards/{a}/items/{ids['p1']}", json={"note": "A's note"})
    a_boards, a_cards = as_("a").get("/v1/boards").json(), as_("a").get(f"/v1/boards/{a}/items")
    b = as_("b")
    assert b.get("/v1/boards").json() == []
    assert b.get("/v1/boards", params={"archived": True}).json() == []
    assert b.post("/v1/boards", json={"name": "Mine"}).status_code == 201  # A's name is free
    one = {"product_ids": [str(ids["p2"])]}
    item = f"/v1/boards/{a}/items/{ids['p1']}"
    for response in (
        b.patch(f"/v1/boards/{a}", json={"name": "Taken"}),
        b.post(f"/v1/boards/{a}/archive"),
        b.post(f"/v1/boards/{a}/unarchive"),
        b.delete(f"/v1/boards/{a}"),
        b.get(f"/v1/boards/{a}/items"),
        b.get(f"/v1/boards/{a}/items", params={"format": "csv"}),
        b.post(f"/v1/boards/{a}/items", json=one),
        b.patch(item, json={"note": "B's note", "position": 0}),
        b.delete(item),
        b.post(f"/v1/boards/{a}/items/send-to-testing", json=one),
    ):
        assert (response.status_code, response.json()["code"]) == (404, "not_found")
    assert as_("a").get("/v1/boards").json() == a_boards
    assert as_("a").get(f"/v1/boards/{a}/items").json() == a_cards.json()
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(ProductTest)) == 0
        # The database refuses a card on another workspace's board.
        session.add(
            BoardItem(
                workspace_id=ids["workspace_b"], board_id=UUID(a), product_id=ids["p3"], position=0
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def observe(session: Session, model: type[Any], source_id: int, **values: Any) -> None:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id, run_id=run.id, captured_at=AT, request={}, bytes=1,
        sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    session.add(model(captured_at=AT, raw_payload_id=payload.id, observed_for=DAY, **values))
    session.flush()


def stocked(session: Session, name: str) -> UUID:
    """A product with every card stat: a $29.99–$34.99 store listing, a $7.40 CJ offer with a
    $4.10 US quote, and yesterday's Trend 70, Saturation 40 and Rising."""
    product = Product(name=name)
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add_all([product, store, supplier])
    session.flush()
    shelf, offer = (
        Listing(
            source_id=source,
            external_id=uuid4().hex,
            url="https://example.test/p",
            title=name,
            product_id=product.id,
            **owner,
        )  # fmt: skip
        for source, owner in ((1, {"store_id": store.id}), (2, {"supplier_id": supplier.id}))
    )
    session.add_all([shelf, offer])
    session.flush()
    observe(
        session, ListingSnapshot, 1, values_hash="h", currency="USD", price_min_minor=2999,
        price_max_minor=3499, listing_id=shelf.id,
    )  # fmt: skip
    observe(
        session, ListingSnapshot, 2, values_hash="h", currency="USD", price_min_minor=740,
        listing_id=offer.id,
    )  # fmt: skip
    observe(
        session, ShippingOption, 2, listing_id=offer.id, destination_country="US", quantity=1,
        method="CJPacket", cost_minor=410, currency="USD", min_days=1, max_days=8,
    )  # fmt: skip
    explanation = Explanation(
        model_version="000-fixture00000", config_digest="f" * 64, components=(), missing=(),
        coverage=0.0,
    )  # fmt: skip
    rows = [
        ScoreRow(product.id, DAY, "trend", 70.0, explanation),
        ScoreRow(product.id, DAY, "saturation", 40.0, explanation),
        ScoreRow(product.id, DAY, "lifecycle", None, explanation, "rising"),
    ]
    assert write(session, rows) == 3
    return product.id


@pytest.fixture
def stats(boards: tuple[As, dict[str, UUID]], db_engine: Engine) -> tuple[TestClient, str, UUID]:
    """Workspace A's board holding "Lamp", which has every stat; A has settings (duty 0)."""
    as_, ids = boards
    with Session(db_engine) as session:
        session.add(WorkspaceSettings(workspace_id=ids["workspace_a"], duty_default_bps=0, **FEES))
        lamp = stocked(session, "Lamp")
        session.commit()
    client = as_("a")
    board = client.post("/v1/boards", json={"name": "Stats"}).json()["id"]
    assert client.post(f"/v1/boards/{board}/items", json={"product_ids": [str(lamp)]}).is_success
    return client, board, lamp


def card_of(client: TestClient, board: str, product_id: UUID) -> Any:
    items = client.get(f"/v1/boards/{board}/items").json()["items"]
    return next(item for item in items if item["product_id"] == str(product_id))


@pytest.mark.db
def test_a_card_carries_its_stats_each_traced(stats: tuple[TestClient, str, UUID]) -> None:
    client, board, lamp = stats
    card = card_of(client, board, lamp)
    at = AT.isoformat().replace("+00:00", "Z")
    low, high = card["price_min_minor"], card["price_max_minor"]
    assert (low["value"], high["value"], card["currency"]) == (2999, 3499, "USD")
    assert (low["source"], low["as_of"], low["raw_payload_id"] is not None) == (
        "shopify_stores",
        at,
        True,
    )
    margin = card["best_margin_minor"]
    assert (margin["value"] > 0, margin["margin_bps"] > 0, margin["as_of"]) == (True, True, at)
    assert (card["trend"]["value"], card["saturation"]["value"]) == (70.0, 40.0)
    assert (card["lifecycle"]["stage"], card["lifecycle"]["value"]) == ("rising", None)
    assert card["trend"]["model_version"] == "000-fixture00000" and card["trend"]["as_of"]
    assert card["merged_into_id"] is None
    # A note's PATCH answers the same card, stats and all.
    noted = client.patch(f"/v1/boards/{board}/items/{lamp}", json={"note": "x"}).json()
    assert noted == card | {"note": "x"}


@pytest.mark.db
def test_a_merged_card_names_its_survivor_and_shows_its_stats(
    boards: tuple[As, dict[str, UUID]], stats: tuple[TestClient, str, UUID], db_engine: Engine
) -> None:
    """Cards aren't rewritten when a merge lands after the add (DEC-319 e): the card keeps its
    product and carries the survivor, through any chain of merges, whose stats it shows."""
    _, ids = boards
    client, board, lamp = stats
    add(client, board, ids, "p2")
    with Session(db_engine) as session:
        session.get_one(Product, ids["p0"]).merged_into_id = lamp
        session.get_one(Product, ids["p2"]).merged_into_id = ids["merged"]  # merged → middle → p0
        session.commit()
    card = card_of(client, board, ids["p2"])
    assert (card["name"], card["merged_into_id"]) == ("Product 2", str(lamp))
    assert card["trend"] == card_of(client, board, lamp)["trend"]
    assert card["price_min_minor"]["value"] == 2999
    assert card_of(client, board, lamp)["merged_into_id"] is None


@pytest.mark.db
def test_a_fee_change_moves_best_margin_on_the_next_read(
    boards: tuple[As, dict[str, UUID]], stats: tuple[TestClient, str, UUID], db_engine: Engine
) -> None:
    _, ids = boards
    client, board, lamp = stats
    before = card_of(client, board, lamp)["best_margin_minor"]
    with Session(db_engine) as session:
        session.get_one(WorkspaceSettings, ids["workspace_a"]).payment_fee_bps = 1290
        session.commit()
    after = card_of(client, board, lamp)["best_margin_minor"]
    # 10 % more of the $29.99 price goes to fees: $3.00 less margin.
    assert before["value"] - after["value"] == 300
    assert after["margin_bps"] < before["margin_bps"]


def statements(db_engine: Engine, request: Callable[[], object]) -> int:
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
def test_a_page_of_50_cards_runs_as_many_queries_as_a_page_of_1(
    stats: tuple[TestClient, str, UUID], db_engine: Engine
) -> None:
    client, board, _ = stats
    with Session(db_engine) as session:
        filler = [stocked(session, f"Filler {i}") for i in range(50)]
        session.commit()
    body = {"product_ids": [str(product) for product in filler]}
    assert client.post(f"/v1/boards/{board}/items", json=body).is_success
    url = f"/v1/boards/{board}/items"
    one, fifty = (
        statements(db_engine, partial(client.get, url, params={"limit": limit}))
        for limit in (1, 50)
    )
    assert one == fifty
    print(f"query count, a page of cards: {fifty}")  # reported in docs/reports/imp-454.md


def board_csv(client: TestClient, board: str, file: str) -> list[dict[str, str]]:
    """A board's CSV, checked for the format every export shares (DEC-316)."""
    response = client.get(f"/v1/boards/{board}/items", params={"format": "csv", "limit": 1})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="pulso_board_{file}_{datetime.now(UTC).date().isoformat()}.csv"'
    )
    assert response.content.startswith(b"\xef\xbb\xbf")  # the BOM, for Excel on Windows
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0] == ",".join(BOARD_CSV)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert response.headers["x-total-count"] == str(len(rows))
    return rows


@pytest.mark.db
def test_a_board_exports_every_card_in_order_with_the_jsons_numbers(
    boards: tuple[As, dict[str, UUID]],
    stats: tuple[TestClient, str, UUID],
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One row per card in board order, the limit ignored, places running on across chunks;
    each stat as the JSON card has it, a missing one an empty cell, never 0 (DEC-040)."""
    _, ids = boards
    client, board, lamp = stats
    monkeypatch.setattr("pulso_api.csv_export.CHUNK", 1)
    add(client, board, ids, "p2", "p3")
    note = {"note": '=HYPERLINK("https://x.test")', "position": 0}
    assert client.patch(f"/v1/boards/{board}/items/{ids['p2']}", json=note).is_success
    assert client.patch("/v1/boards/" + board, json={"name": "Q4 gifts: <$40!"}).is_success
    with Session(db_engine) as session:
        session.get_one(Product, ids["p3"]).merged_into_id = lamp  # after the add
        session.commit()
    rows = board_csv(client, board, "q4-gifts-40")
    order = [ids["p2"], lamp, ids["p3"]]
    assert [(row["position"], row["product_id"]) for row in rows] == [
        (str(place), str(product)) for place, product in enumerate(order, 1)
    ]
    empty, lamp_row, merged = rows
    card = card_of(client, board, lamp)
    margin, at = card["best_margin_minor"], AT.isoformat().replace("+00:00", "Z")
    assert (lamp_row["product"], lamp_row["note"], lamp_row["merged_into_id"]) == ("Lamp", "", "")
    assert (lamp_row["price_min"], lamp_row["price_max"], lamp_row["currency"]) == (
        "29.99",
        "34.99",
        "USD",
    )
    assert lamp_row["best_margin"] == str(major(margin["value"]))
    assert lamp_row["best_margin_pct"] == str(Decimal(margin["margin_bps"]).scaleb(-2))
    assert lamp_row["trend"] == str(card["trend"]["value"]) == "70.0"
    assert (lamp_row["lifecycle"], lamp_row["saturation"]) == ("rising", "40.0")
    assert lamp_row["added_at"] == card["added_at"].replace("+00:00", "Z")
    assert (lamp_row["price_as_of"], lamp_row["best_margin_as_of"]) == (at, at)
    for kind in ("trend", "lifecycle", "saturation"):
        assert lamp_row[f"{kind}_as_of"] == card[kind]["as_of"].replace("+00:00", "Z")
    assert merged | {"position": "2", "product_id": str(lamp)} == lamp_row | {
        "product": "Product 3",
        "merged_into_id": str(lamp),
        "added_at": merged["added_at"],
    }
    assert empty["note"] == '\'=HYPERLINK("https://x.test")'  # never run as a formula
    assert {key for key, value in empty.items() if value == ""} == {
        "price_min",
        "price_max",
        "best_margin",
        "best_margin_pct",
        "trend",
        "lifecycle",
        "saturation",
        "merged_into_id",
        "price_as_of",
        "best_margin_as_of",
        "trend_as_of",
        "lifecycle_as_of",
        "saturation_as_of",
    }
    assert (empty["currency"], empty["stale"]) == ("USD", "false")
