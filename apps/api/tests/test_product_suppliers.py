"""GET /v1/products/{id}/suppliers (UX-6, R-16, DEC-264) on fixture rows only."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.profit import reference_price
from pulso_core.db import Base
from pulso_core.landed_cost import best
from pulso_core.landed_cost_loader import calculate
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    RawPayload,
    ShippingOption,
    Source,
    Store,
    Supplier,
    SupplierOffer,
    Workspace,
    WorkspaceSettings,
)

SHOPIFY, CJ = 1, 2  # seeded source ids
NOW = datetime.now(UTC).replace(microsecond=0)
FEES = {"duty_default_bps": 2000, "payment_fee_bps": 290, "payment_fee_fixed_minor": 30}


def test_suppliers_require_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}/suppliers").status_code == 401


@pytest.mark.parametrize("query", ["country=CN", "limit=0", "limit=201"])
def test_suppliers_validate_the_query(client: TestClient, query: str) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    assert client.get(f"/v1/products/{uuid4()}/suppliers?{query}").status_code == 422


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def get(api: TestClient, workspace_id: UUID, path: str, status: int = 200) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.get(path, follow_redirects=False)
    assert response.status_code == status, response.text
    return response.json() if status == 200 else response


def calc(api: TestClient, workspace_id: UUID, **body: Any) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.post(
        "/v1/profit/calc", json={k: str(v) if isinstance(v, UUID) else v for k, v in body.items()}
    )
    assert response.status_code == 200, response.text
    return response.json()


def observe[T: Base](session: Session, model: type[T], source_id: int, **values: Any) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id,
        run_id=run.id,
        captured_at=NOW,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=NOW, raw_payload_id=payload.id, observed_for=NOW.date(), **values)
    session.add(row)
    session.flush()
    return row


def workspace(session: Session, **settings: Any) -> UUID:
    row = Workspace(name="Workspace")
    session.add(row)
    session.flush()
    session.add(WorkspaceSettings(workspace_id=row.id, **settings))
    return row.id


def lamp(session: Session, price: int = 2999) -> Product:
    """A product with one live USD store price (an imported one: DEC-261) and no supplier yet."""
    product = Product(name="Sunset lamp")
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    session.add_all([product, store])
    session.flush()
    shop = Listing(
        source_id=SHOPIFY,
        external_id=uuid4().hex,
        url="https://shop.example.test/p",
        title="Sunset lamp",
        product_id=product.id,
        store_id=store.id,
    )
    session.add(shop)
    session.flush()
    observe(
        session, ListingSnapshot, SHOPIFY, listing_id=shop.id, values_hash="h", currency="USD",
        price_min_minor=price,
    )  # fmt: skip
    return product


def supplier(
    session: Session,
    product: Product,
    cost: int,
    freight: int | None = None,
    days: tuple[int, int] | None = None,
    method: str = "CJPacket",
    supplier_row: Supplier | None = None,
    **snapshot: Any,
) -> int:
    """A live CJ listing of `product` at `cost`, with a US quote when `freight` is given."""
    if supplier_row is None:
        supplier_row = Supplier(platform="cj", external_id=uuid4().hex, name="CJ Dropshipping")
        session.add(supplier_row)
        session.flush()
    listing = Listing(
        source_id=CJ,
        external_id=uuid4().hex,
        url=f"https://cjdropshipping.com/product/{uuid4().hex}.html",
        title="Sunset lamp, 16 colours",
        product_id=product.id,
        supplier_id=supplier_row.id,
        last_seen_at=NOW,
    )
    session.add(listing)
    session.flush()
    observe(
        session, ListingSnapshot, CJ, listing_id=listing.id, values_hash="h", currency="USD",
        price_min_minor=cost, **snapshot,
    )  # fmt: skip
    if freight is not None:
        observe(
            session, ShippingOption, CJ, listing_id=listing.id, destination_country="US",
            method=method, cost_minor=freight, currency="USD",
            min_days=days[0] if days else None, max_days=days[1] if days else None,
        )  # fmt: skip
    return listing.id


def suppliers(api: TestClient, ws: UUID, product_id: UUID, query: str = "") -> Any:
    return get(api, ws, f"/v1/products/{product_id}/suppliers{query}")


def engine_picks(db_engine: Engine, ws: UUID, product_id: UUID, ids: list[int]) -> tuple[Any, Any]:
    """The picks from the engine itself: best() for margin, the chosen quote's days for speed."""
    with Session(db_engine) as session:
        settings = session.get_one(WorkspaceSettings, ws)
        price = reference_price(session, product_id)
        calcs = {
            i: calculate(session, settings, product_id, reference_price=price, listing_id=i)
            for i in ids
        }
    quoted = [i for i in ids if calcs[i].days[1] is not None]
    landed = {i: calcs[i].cost.landed_cost_minor for i in ids}
    fastest = min(
        quoted,
        key=lambda i: (calcs[i].days[1], landed[i] is None, landed[i] or 0, i),
        default=None,
    )
    return best({i: calc.cost for i, calc in calcs.items()}), fastest


@pytest.mark.db
def test_the_picks_are_the_engines_and_an_unquoted_cheap_supplier_never_wins(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        cheap = supplier(session, product, 100)  # $1.00 but never quoted to the US
        dear = supplier(session, product, 700, 485, (8, 12))
        margin = supplier(session, product, 620, 485, (8, 12))
        fast = supplier(session, product, 900, 300, (3, 5), method="YunExpress")
        tied = supplier(session, product, 950, 300, (2, 5))  # as fast at most; dearer landed cost
        session.commit()
        product_id = product.id

    body = suppliers(api, ws, product_id, "?country=US")
    by_id = {row["listing_id"]: row for row in body["rows"]}
    expected = engine_picks(db_engine, ws, product_id, [cheap, dear, margin, fast, tied])
    assert expected == (margin, fast)
    assert (body["picks"]["best_margin"]["listing_id"], body["picks"]["fastest"]["listing_id"]) == (
        margin,
        fast,
    )
    assert body["picks"]["best_margin"] == by_id[margin]  # the pick card shows the row itself
    assert by_id[margin]["picks"] == ["best_margin"] and by_id[fast]["picks"] == ["fastest"]
    assert by_id[cheap]["picks"] == by_id[dear]["picks"] == by_id[tied]["picks"] == []
    unquoted = by_id[cheap]["cost"]
    assert (unquoted["complete"], unquoted["missing"], unquoted["margin_minor"]) == (
        False,
        ["freight_missing"],
        None,
    )
    assert by_id[margin]["cost"]["margin_minor"] == 1653  # 2999 − landed 1229 − payment fee 117
    # Best margin first, then the incomplete row; the cheapest landed cost doesn't jump the queue.
    assert [row["listing_id"] for row in body["rows"]] == [margin, dear, fast, tied, cheap]


@pytest.mark.db
def test_each_row_costs_exactly_what_the_profit_tab_gets_for_that_supplier(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        ids = [supplier(session, product, 620, 485, (8, 12)), supplier(session, product, 400)]
        session.commit()
        product_id = product.id

    rows = suppliers(api, ws, product_id)["rows"]
    for row in rows:
        same = calc(api, ws, product_id=product_id, supplier_listing_id=row["listing_id"])
        assert row["cost"] == same
    assert sorted(row["listing_id"] for row in rows) == sorted(ids)


@pytest.mark.db
def test_duty_not_set_leaves_no_best_margin_while_fastest_still_picks(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)  # no duty default: every row reads duty_not_set (R-16)
        product = lamp(session)
        slow = supplier(session, product, 620, 485, (8, 12))
        fast = supplier(
            session, product, 700, 485, (3, 12)
        )  # same max days; landed withheld for both
        session.commit()
        product_id = product.id

    body = suppliers(api, ws, product_id)
    assert body["picks"]["best_margin"] is None
    assert body["picks"]["fastest"]["listing_id"] == slow  # max days tie, no landed cost → lower id
    assert engine_picks(db_engine, ws, product_id, [slow, fast]) == (None, slow)
    assert {tuple(row["cost"]["missing"]) for row in body["rows"]} == {("duty_not_set",)}


@pytest.mark.db
def test_a_known_out_of_stock_row_never_wins_a_pick(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        gone = supplier(session, product, 500, 300, (3, 5), stock=0)
        sold_out = supplier(session, product, 510, 300, (3, 5), available=False)
        kept = supplier(session, product, 620, 485, (8, 12), stock=40)
        session.commit()
        product_id = product.id

    body = suppliers(api, ws, product_id)
    by_id = {row["listing_id"]: row for row in body["rows"]}
    assert (body["picks"]["best_margin"]["listing_id"], body["picks"]["fastest"]["listing_id"]) == (
        kept,
        kept,
    )
    assert [by_id[i]["in_stock"] for i in (gone, sold_out, kept)] == [False, False, True]
    # Out-of-stock rows follow the in-stock ones whatever their margin: the first row is the pick.
    assert [row["listing_id"] for row in body["rows"]] == [kept, gone, sold_out]
    assert by_id[gone]["stock"]["value"] == 0 and by_id[gone]["cost"]["complete"]


@pytest.mark.db
def test_supplier_terms_carry_their_own_provenance_or_no_source(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        rated = Supplier(
            platform="cj", external_id="agent", name="Shenzhen Lamp Co.", rating=Decimal("4.60"),
            years_active=6, country="CN", url="https://cj.example.test/s",
        )  # fmt: skip
        session.add(rated)
        session.flush()
        full = supplier(
            session, product, 620, 485, (8, 12), supplier_row=rated,
            sold_count=1840, rating=Decimal("4.70"), review_count=312, stock=40,
        )  # fmt: skip
        window = supplier(session, product, 640, orders_window=96, window_days=30)
        bare = supplier(session, product, 660)
        session.add_all(
            [
                SupplierOffer(
                    listing_id=full,
                    moq=2,
                    warehouse_country="US",
                    bulk_tiers=[
                        {"min_quantity": 10, "unit_minor": 590},
                        {"bad": "tier"},
                        {"min_quantity": 50, "unit_minor": "5.40"},
                    ],
                ),
            ]
        )
        session.commit()
        product_id = product.id

    rows = {row["listing_id"]: row for row in suppliers(api, ws, product_id)["rows"]}
    row = rows[full]
    assert (row["supplier_name"], row["platform"], row["supplier_country"]) == (
        "Shenzhen Lamp Co.",
        "cj",
        "CN",
    )
    assert (row["warehouse_country"], row["unit_cost_minor"], row["currency"]) == ("US", 620, "USD")
    assert row["url"].startswith("https://cjdropshipping.com/product/")
    as_of = NOW.isoformat().replace("+00:00", "Z")
    for name, value in (("orders", 1840), ("rating", 470), ("stock", 40), ("moq", 2)):
        assert (row[name]["value"], row[name]["source"], row[name]["source_name"]) == (
            value,
            "cj",
            "CJ Dropshipping",
        ), name
        assert row[name]["as_of"] == as_of, name
    assert (row["orders"]["semantics"], row["rating"]["count"]) == ("lifetime", 312)
    assert row["years_active"]["value"] == 6 and row["years_active"]["raw_payload_id"] is None
    assert row["bulk_tiers"] == [
        {"min_quantity": 10, "unit_minor": 590, "currency": "USD", "as_of": as_of}
    ]  # a tier without the two integers is left out, never guessed
    assert (rows[window]["orders"]["semantics"], rows[window]["orders"]["window_days"]) == (
        "window",
        30,
    )
    for name in ("orders", "rating", "years_active", "moq", "stock"):
        assert rows[bare][name]["value"] is None and rows[bare][name]["reason"], name
    assert rows[bare]["bulk_tiers"] == [] and rows[bare]["warehouse_country"] is None


@pytest.mark.db
def test_keyset_pages_walk_every_row_once_in_order(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        for cost in (620, 700, 300, 900, 650):
            supplier(session, product, cost, 485 if cost != 300 else None, (8, 12))
        session.commit()
        product_id = product.id

    whole = [row["listing_id"] for row in suppliers(api, ws, product_id)["rows"]]
    walked: list[int] = []
    cursor = None
    while True:
        query = "?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = suppliers(api, ws, product_id, query)
        walked += [row["listing_id"] for row in page["rows"]]
        assert page["picks"]["best_margin"] is not None  # picks cover every row on every page
        if (cursor := page["next_cursor"]) is None:
            break
    assert walked == whole and len(whole) == 5


@pytest.mark.db
def test_unknown_merged_empty_and_bad_cursor(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        delisted = supplier(session, product, 300, 200, (3, 5))  # a delisted listing never shows
        session.get_one(Listing, delisted).delisted_at = NOW
        gone = Product(name="Old lamp", merged_into_id=product.id)
        session.add(gone)
        session.commit()
        product_id, gone_id = product.id, gone.id

    empty = suppliers(api, ws, product_id)
    assert empty == {
        "country": "US",
        "rows": [],
        "next_cursor": None,
        "picks": {"best_margin": None, "fastest": None},
        "as_of": None,
    }
    get(api, ws, f"/v1/products/{uuid4()}/suppliers", 404)
    moved = get(api, ws, f"/v1/products/{gone_id}/suppliers?country=US", 308)
    assert moved.headers["location"] == f"../{product_id}/suppliers?country=US"
    assert get(api, ws, f"/v1/products/{product_id}/suppliers?cursor=x", 422).json()["code"] == (
        "invalid_cursor"
    )


@pytest.mark.db
def test_a_stale_listing_reads_stale(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        listing = supplier(session, product, 620, 485, (8, 12))
        session.get_one(Listing, listing).last_seen_at = NOW - timedelta(days=3)
        session.get_one(Source, CJ).config = {"expected_interval": 86_400}
        session.commit()
        product_id = product.id

    row = suppliers(api, ws, product_id)["rows"][0]
    assert row["stale"] and row["last_seen"] == (NOW - timedelta(days=3)).isoformat().replace(
        "+00:00", "Z"
    )
    assert suppliers(api, ws, product_id)["as_of"] == row["last_seen"]
