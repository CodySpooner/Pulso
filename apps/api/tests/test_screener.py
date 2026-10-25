import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.product_scores import NO_ROW
from pulso_api.routers.products import NO_PRICE, NO_SETTINGS, NO_SIGNAL
from pulso_api.routers.screener import NO_ACCELERATION, NO_RATING, NO_SHIPPING
from pulso_core.db import Base
from pulso_core.models import (
    Category,
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    Workspace,
    WorkspaceSettings,
)
from pulso_core.scores import Explanation, Kind, ScoreRow, Stage, write

# WF-1 part a (DEC-336): every §6.3 v1 filter narrows this fixture set; a missing value never
# passes a filter; merged and emptied products never list.
SHOPIFY, CJ = 1, 2  # seeded source ids
NOW = datetime.now(UTC)
DAY = NOW.date() - timedelta(days=1)  # scored and featured yesterday
AT = datetime.combine(DAY, datetime.min.time(), UTC) + timedelta(hours=6)
FEES = {"payment_fee_bps": 290, "payment_fee_fixed_minor": 30, "returns_bps": 500}
LIVE = ("Lamp", "Mug", "Fan", "Duck", "Bare")  # Bare: no data at all


def test_the_screener_requires_a_session(client: TestClient) -> None:
    assert client.get("/v1/screener").status_code == 401


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def observe[T: Base](
    session: Session, model: type[T], source_id: int, at: datetime = AT, **values: Any
) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id, run_id=run.id, captured_at=at, request={}, bytes=1,
        sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    row = model(captured_at=at, raw_payload_id=payload.id, observed_for=at.date(), **values)
    session.add(row)
    session.flush()
    return row


def listing(session: Session, product: Product, source_id: int, **owner: Any) -> Listing:
    row = Listing(
        source_id=source_id, external_id=uuid4().hex, url="https://example.test/p",
        title=product.name, product_id=product.id, **owner,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row


def score(
    session: Session, product: Product, kind: Kind, value: float | None = None,
    stage: Stage | None = None, reason: str | None = None,
) -> None:  # fmt: skip
    explanation = Explanation(
        model_version="000-fixture00000", config_digest="f" * 64, components=(), missing=(),
        coverage=0.0, reason=reason,
    )  # fmt: skip
    assert write(session, [ScoreRow(product.id, DAY, kind, value, explanation, stage)]) == 1


def feature(product: Product, days_ago: int, v7: float, growth: float) -> ProductDailyFeature:
    return ProductDailyFeature(
        product_id=product.id, feature_date=DAY - timedelta(days=days_ago), family="shp_inv",
        feature_version="002-fixture", velocity_7d=v7, growth_7d=growth, coverage=1,
        has_gap=False,
    )  # fmt: skip


def build(
    session: Session,
    name: str,
    *,
    price: int | None = None,
    cost: int | None = None,
    ship: tuple[int, int | None] | None = None,  # (freight minor, max days)
    rating: tuple[str | None, str | None] = (None, None),  # (snapshot's, supplier's)
    growth: tuple[float, float, float | None] | None = None,  # (V7, G7, G7 a week earlier)
    trend: float | None | tuple[None, str] = None,  # (None, reason): a NULL row
    saturation: float | None = None,
    stage: Stage | tuple[None, str] | None = None,
    category: int | None = None,
) -> Product:
    product = Product(name=name, category_id=category)
    session.add(product)
    session.flush()
    if price is not None:
        store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
        session.add(store)
        session.flush()
        shelf = listing(session, product, SHOPIFY, store_id=store.id)
        observe(
            session, ListingSnapshot, SHOPIFY, values_hash="h", currency="USD",
            price_min_minor=price, listing_id=shelf.id,
        )  # fmt: skip
    if cost is not None:
        supplier = Supplier(
            platform="cj", external_id=uuid4().hex, name="CJ supplier",
            rating=rating[1] and float(rating[1]),
        )  # fmt: skip
        session.add(supplier)
        session.flush()
        offer = listing(session, product, CJ, supplier_id=supplier.id)
        observe(
            session, ListingSnapshot, CJ, values_hash="h", currency="USD", price_min_minor=cost,
            rating=rating[0] and float(rating[0]), listing_id=offer.id,
        )  # fmt: skip
        if ship is not None:
            # A faster method quoted two days earlier and since dropped: never the fastest.
            for at, method, days in (
                (AT - timedelta(days=2), "Gone", 1),
                (AT, "CJPacket", ship[1]),
            ):
                observe(
                    session, ShippingOption, CJ, at, listing_id=offer.id, destination_country="US",
                    quantity=1, method=method, cost_minor=ship[0], currency="USD", min_days=1,
                    max_days=days,
                )  # fmt: skip
    if growth is not None:
        v7, g7, before = growth
        session.add(feature(product, 0, v7, g7))
        if before is not None:
            session.add(feature(product, 7, v7, before))
        session.flush()
    if isinstance(trend, tuple):
        score(session, product, "trend", reason=trend[1])
    elif trend is not None:
        score(session, product, "trend", trend)
    if saturation is not None:
        score(session, product, "saturation", saturation)
    if isinstance(stage, tuple):
        score(session, product, "lifecycle", reason=stage[1])
    elif stage is not None:
        score(session, product, "lifecycle", stage=stage, reason="fixture rule")
    return product


def catalog(session: Session) -> dict[str, UUID]:
    """Five live products, each missing some metrics, and two that never list."""
    session.add_all(
        [
            Category(id=1, name="Lamps", path="Home > Lamps"),
            Category(id=2, name="Mugs", path="Mugs"),
        ]
    )
    lamp = dict(
        price=2999, cost=740, ship=(410, 8), rating=("4.60", "3.00"), growth=(30.0, 0.40, 0.20),
        trend=70.0, saturation=40.0, stage="rising", category=1,
    )  # fmt: skip
    products = [
        build(session, "Lamp", **lamp),  # type: ignore[arg-type]
        build(
            session,
            "Mug",
            price=1500,
            cost=900,
            ship=(300, 15),
            rating=(None, "4.00"),
            growth=(10.0, -0.10, 0.05),
            trend=50.0,
            saturation=80.0,
            stage="peaking",
            category=2,
        ),  # fmt: skip
        build(
            session,
            "Fan",
            price=4000,
            trend=(None, "every input missing"),
            stage=(None, "no rule matched"),
            category=1,
        ),  # fmt: skip
        build(
            session,
            "Duck",
            cost=500,
            ship=(200, None),
            growth=(5.0, 0.10, None),
            trend=50.0,
            stage="emerging",
        ),  # fmt: skip
        build(session, "Merged", **lamp),  # type: ignore[arg-type]
        build(session, "Empty", **lamp),  # type: ignore[arg-type]
        build(session, "Bare"),
    ]
    ids = {product.name: product.id for product in products}
    products[4].merged_into_id = ids["Lamp"]
    products[5].status = "empty"
    session.flush()
    return ids


def as_workspace(api: TestClient, workspace_id: UUID) -> TestClient:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    return api


@pytest.fixture
def screened(api: TestClient, db_engine: Engine) -> tuple[TestClient, dict[str, UUID]]:
    with Session(db_engine) as session:
        workspace = Workspace(name="A")
        session.add(workspace)
        session.flush()
        session.add(WorkspaceSettings(workspace_id=workspace.id, duty_default_bps=0, **FEES))
        ids = catalog(session)
        session.commit()
        return as_workspace(api, workspace.id), ids


def screen(api: TestClient, status: int = 200, **params: Any) -> Any:
    if isinstance(params.get("filters"), dict):
        params["filters"] = json.dumps(params["filters"])
    response = api.get("/v1/screener", params=params)
    assert response.status_code == status, response.text
    return response.json()


def names(body: Any, ids: dict[str, UUID]) -> set[str]:
    by_id = {str(product): name for name, product in ids.items()}
    return {by_id[row["id"]] for row in body["items"]}


@pytest.mark.db
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({}, set(LIVE)),  # never Merged, never Empty
        ({"margin_bps_min": 3000}, {"Lamp"}),  # 5275 bps; Mug 1007; Fan and Duck incomplete
        ({"margin_bps_max": 3000}, {"Mug"}),
        ({"velocity_min": 20}, {"Lamp"}),
        ({"velocity_max": 20}, {"Mug", "Duck"}),  # Fan has no demand family
        ({"velocity_min": 30, "price_max": 2999}, {"Lamp"}),  # bounds are inclusive
        ({"acceleration_min": 0}, {"Lamp"}),  # +0.20; Mug −0.15; Duck has no G7 a week earlier
        ({"acceleration_max": 0}, {"Mug"}),
        ({"saturation_min": 50}, {"Mug"}),
        ({"saturation_max": 50}, {"Lamp"}),  # Fan and Duck have no saturation row
        ({"price_min": 2000}, {"Lamp", "Fan"}),  # Duck has no store listing
        ({"price_max": 2000}, {"Mug"}),
        ({"supplier_rating_min": 450}, {"Lamp"}),  # the snapshot's 4.60 over its supplier's 3.00
        ({"supplier_rating_max": 450}, {"Mug"}),  # the supplier's own 4.00
        ({"ship_days_us_max": 10}, {"Lamp"}),
        ({"ship_days_us_min": 10}, {"Mug"}),  # Duck's quote gives no max days
        ({"lifecycle": ["rising", "emerging"]}, {"Lamp", "Duck"}),  # Fan's stage is NULL
        ({"lifecycle": ["peaking"]}, {"Mug"}),
        ({"category": 1}, {"Lamp", "Fan"}),
        ({"price_min": 2000, "lifecycle": ["rising"]}, {"Lamp"}),  # AND
    ],
    ids=lambda value: json.dumps(value) if isinstance(value, dict) else None,
)
def test_each_filter_narrows_and_a_missing_value_never_passes(
    screened: tuple[TestClient, dict[str, UUID]], filters: dict[str, Any], expected: set[str]
) -> None:
    api, ids = screened
    assert names(screen(api, filters=filters), ids) == expected


@pytest.mark.db
def test_rows_trace_every_metric_and_name_each_missing_one(
    screened: tuple[TestClient, dict[str, UUID]],
) -> None:
    api, ids = screened
    rows = {row["title"]: row for row in screen(api)["items"]}
    lamp, mug, fan, duck, bare = (rows[name] for name in LIVE)
    at = AT.isoformat().replace("+00:00", "Z")
    assert (lamp["price_minor"]["value"], lamp["price_minor"]["source"]) == (2999, "shopify_stores")
    assert lamp["price_minor"]["as_of"] == at
    assert (lamp["margin"]["value"], lamp["margin"]["margin_bps"]) == (1582, 5275)
    assert (lamp["velocity"]["value"], lamp["velocity"]["family"]) == (30, "shp_inv")
    accel = lamp["acceleration"]
    assert (round(accel["value"], 6), accel["source"]) == (0.2, "shopify_stores")
    assert accel["as_of"] == lamp["velocity"]["as_of"]
    assert (lamp["supplier_rating"]["value"], lamp["supplier_rating"]["as_of"]) == (460, at)
    assert lamp["supplier_rating"]["raw_payload_id"] is not None  # the snapshot's
    assert (lamp["ship_days_us"]["value"], lamp["ship_days_us"]["source"]) == (8, "cj")
    assert (lamp["trend"]["value"], lamp["saturation"]["value"]) == (70.0, 40.0)
    assert (lamp["lifecycle"]["stage"], lamp["lifecycle"]["reason"]) == ("rising", None)
    assert lamp["opportunity"]["value"] is not None and lamp["opportunity"]["missing"] == ["risk"]
    # The supplier's own rating has no capture: as of the listing's last sighting, no payload.
    assert (mug["supplier_rating"]["value"], mug["supplier_rating"]["raw_payload_id"]) == (
        400,
        None,
    )
    # Missing values are null with a reason, never 0 (DEC-040).
    assert fan["margin"] == {
        "value": None,
        "reason": "Needs a supplier price and a freight quote.",
        "missing": ["supplier_cost_missing", "freight_missing"],
    }
    assert fan["velocity"] == fan["acceleration"] == {"value": None, "reason": NO_SIGNAL}
    assert fan["supplier_rating"] == {"value": None, "reason": NO_RATING}
    assert fan["ship_days_us"] == {"value": None, "reason": NO_SHIPPING}
    assert (fan["trend"]["value"], fan["trend"]["reason"]) == (None, "every input missing")
    assert fan["saturation"] == {"value": None, "reason": NO_ROW}
    assert (fan["lifecycle"]["stage"], fan["lifecycle"]["reason"]) == (None, "no rule matched")
    assert duck["price_minor"] == {"value": None, "reason": NO_PRICE}
    assert duck["acceleration"] == {"value": None, "reason": NO_ACCELERATION}
    assert duck["ship_days_us"] == {"value": None, "reason": NO_SHIPPING}
    metrics = ("price_minor", "margin", "velocity", "acceleration", "supplier_rating")
    metrics += ("ship_days_us", "trend", "saturation", "lifecycle", "opportunity")
    assert all(bare[key]["value"] is None and bare[key]["reason"] for key in metrics)


def metric(row: Any, key: str) -> float | None:
    """A row's value of a sort key, as the response shows it."""
    field, name = {"margin_bps": ("margin", "margin_bps"), "price": ("price_minor", "value")}.get(
        key, (key, "value")
    )
    value: float | None = row[field].get(name)
    return value


SORTS = (
    "trend",
    "opportunity",
    "margin_bps",
    "velocity",
    "acceleration",
    "saturation",
    "price",
    "supplier_rating",
    "ship_days_us",
)


@pytest.mark.db
@pytest.mark.parametrize("sort", SORTS)
def test_each_sort_orders_nulls_last_and_a_cursor_walk_lists_each_row_once(
    screened: tuple[TestClient, dict[str, UUID]], sort: str
) -> None:
    api, ids = screened
    for order in ("desc", "asc"):
        everything = screen(api, sort=sort, order=order)["items"]
        sign = -1 if order == "desc" else 1
        values = {UUID(row["id"]): metric(row, sort) for row in everything}
        expected = sorted(
            values, key=lambda p: (values[p] is None, sign * (values[p] or 0), sign * p.int)
        )
        assert [UUID(row["id"]) for row in everything] == expected, (order, values)
        assert values[expected[-1]] is None  # every sort here has a product missing it
        walked: list[UUID] = []
        cursor = None
        for _ in range(len(LIVE) + 1):  # bounded: a cursor that repeats a row can't loop
            page = screen(
                api, sort=sort, order=order, limit=1, **({"cursor": cursor} if cursor else {})
            )
            walked += [UUID(row["id"]) for row in page["items"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        assert walked == expected
        assert sorted(names({"items": [{"id": str(p)} for p in walked]}, ids)) == sorted(LIVE)


@pytest.mark.db
def test_ties_break_by_id_and_the_cursor_keeps_them(
    screened: tuple[TestClient, dict[str, UUID]],
) -> None:
    api, ids = screened  # Mug and Duck both trend 50.0
    tied = sorted((ids["Mug"], ids["Duck"]), key=lambda p: p.int, reverse=True)
    first = screen(api, sort="trend", limit=2)
    assert [row["id"] for row in first["items"]] == [str(ids["Lamp"]), str(tied[0])]
    second = screen(api, sort="trend", limit=1, cursor=first["next_cursor"])
    assert [row["id"] for row in second["items"]] == [str(tied[1])]
    # Fan's NULL row and Bare's no row are both missing: last, by id.
    missing = sorted((ids["Fan"], ids["Bare"]), key=lambda p: p.int, reverse=True)
    rest = screen(api, sort="trend", cursor=second["next_cursor"])
    assert [row["id"] for row in rest["items"]] == [str(p) for p in missing]


@pytest.mark.db
def test_risk_is_accepted_and_marked_phase_5_but_not_applied(
    screened: tuple[TestClient, dict[str, UUID]],
) -> None:
    api, ids = screened
    body = screen(api, filters={"risk_min": 10, "risk_max": 90})
    assert body["unapplied"] == {"risk_min": "phase_5", "risk_max": "phase_5"}
    assert names(body, ids) == set(LIVE)
    assert screen(api)["unapplied"] == {}


@pytest.mark.db
def test_margin_and_opportunity_are_the_callers_workspaces(
    screened: tuple[TestClient, dict[str, UUID]], db_engine: Engine
) -> None:
    api, ids = screened
    with Session(db_engine) as session:
        other = Workspace(name="B")  # no settings row: no economics row, so no margin
        session.add(other)
        session.commit()
        b = other.id
    a = api.app.dependency_overrides[current_principal]  # type: ignore[attr-defined]
    assert names(screen(api, filters={"margin_bps_min": -10_000}), ids) == {"Lamp", "Mug"}
    as_workspace(api, b)
    assert names(screen(api, filters={"margin_bps_min": -10_000}), ids) == set()
    rows = {row["title"]: row for row in screen(api, sort="opportunity")["items"]}
    assert rows["Lamp"]["margin"] == {"value": None, "reason": NO_SETTINGS, "missing": []}
    assert "margin" in rows["Lamp"]["opportunity"]["missing"]
    api.app.dependency_overrides[current_principal] = a  # type: ignore[attr-defined]
    assert screen(api)["items"][0]["margin"]["margin_bps"] == 5275


@pytest.mark.db
@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"filters": "{"}, "invalid_filters"),
        ({"filters": {"margin_min": 1}}, "invalid_filters"),  # unknown filter
        ({"filters": {"velocity_min": "NaN"}}, "invalid_filters"),
        ({"filters": {"lifecycle": ["booming"]}}, "invalid_filters"),
        ({"cursor": "[1]"}, "invalid_cursor"),
        ({"sort": "risk"}, "validation_error"),  # no risk score to sort until Phase 5
    ],
)
def test_bad_input_is_a_422(
    screened: tuple[TestClient, dict[str, UUID]], params: dict[str, Any], code: str
) -> None:
    api, _ = screened
    assert screen(api, 422, **params)["code"] == code


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
def test_a_page_of_50_runs_as_many_queries_as_a_page_of_1(
    screened: tuple[TestClient, dict[str, UUID]], db_engine: Engine
) -> None:
    """imp-488: the page's scores, margins and metrics are batch reads, whatever its size."""
    api, _ = screened
    with Session(db_engine) as session:
        lamp = dict(
            price=2999, cost=740, ship=(410, 8), rating=("4.60", None),
            growth=(30.0, 0.40, 0.20), trend=70.0, saturation=40.0, stage="rising",
        )  # fmt: skip
        for i in range(50):
            build(session, f"Filler {i}", **lamp)  # type: ignore[arg-type]
        session.commit()
    for sort in ("trend", "opportunity"):
        one, fifty = (
            statements(db_engine, partial(screen, api, sort=sort, limit=limit)) for limit in (1, 50)
        )
        assert one == fifty, sort
        print(f"query count, sort={sort}: {fifty}")  # reported in docs/reports/p4-24.md
