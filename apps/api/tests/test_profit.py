from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, get_args
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.profit import Missing
from pulso_core.db import Base
from pulso_core.landed_cost import MISSING
from pulso_core.models import (
    CollectorRun,
    FxRate,
    Listing,
    ListingSnapshot,
    ListingVariant,
    Product,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    VariantSnapshot,
    Workspace,
    WorkspaceSettings,
)

SHOPIFY, CJ, FX = 1, 2, 4  # seeded source ids
DAY = datetime(2026, 10, 23, 23, 30, tzinfo=UTC)  # already 10-24 east of UTC; the UTC date counts
FEES = {"payment_fee_bps": 290, "payment_fee_fixed_minor": 30, "returns_bps": 500}


def test_calc_requires_a_session(client: TestClient) -> None:
    assert client.post("/v1/profit/calc", json={"product_id": str(uuid4())}).status_code == 401


def test_the_missing_literal_matches_landed_cost() -> None:
    assert get_args(Missing) == MISSING


@pytest.mark.parametrize(
    "field",
    [
        {"quantity": 0},
        {"quantity": 10001},
        {"quantity": "2"},
        {"price_minor": 0},
        {"returns_bps": 10001},
        {"payment_fee_bps": -1},
        {"shopify_fee_bps": 10001},
        {"duty_bps": -1},
        {"duty_bps": 100001},
        {"customs_fee_minor": -1},
        {"payment_fee_fixed_minor": 2**63},
        {"supplier_listing_id": 0},
        {"method": ""},
        {"ddp": "yes"},
        {"cpa_minor": 1500},
    ],
)
def test_calc_validates_bounds(client: TestClient, field: dict[str, Any]) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    response = client.post("/v1/profit/calc", json={"product_id": str(uuid4()), **field})
    assert response.status_code == 422


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def calc(api: TestClient, workspace_id: UUID, status: int = 200, **body: Any) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.post(
        "/v1/profit/calc",
        json={key: str(v) if isinstance(v, UUID) else v for key, v in body.items()},
    )
    assert response.status_code == status, response.text
    return response.json()


def observe[T: Base](
    session: Session, model: type[T], source_id: int, at: datetime = DAY, **values: Any
) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id,
        run_id=run.id,
        captured_at=at,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=at, raw_payload_id=payload.id, **{"observed_for": at.date()} | values)
    session.add(row)
    session.flush()
    return row


def workspace(session: Session, **settings: Any) -> UUID:
    row = Workspace(name="Workspace")
    session.add(row)
    session.flush()
    session.add(WorkspaceSettings(workspace_id=row.id, **settings))
    return row.id


def supplier_listing(session: Session, product: Product, cost: int, currency: str = "USD") -> int:
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add(supplier)
    session.flush()
    row = Listing(
        source_id=CJ,
        external_id=uuid4().hex,
        url="https://cj.example.test/p",
        title="Sunset lamp",
        product_id=product.id,
        supplier_id=supplier.id,
    )
    session.add(row)
    session.flush()
    observe(
        session,
        ListingSnapshot,
        CJ,
        listing_id=row.id,
        values_hash="h",
        currency=currency,
        price_min_minor=cost,
    )
    return row.id


def quote(
    session: Session,
    listing_id: int,
    cost: int,
    *,
    variant_id: int | None = None,
    quantity: int = 1,
    currency: str = "USD",
) -> ShippingOption:
    return observe(
        session,
        ShippingOption,
        CJ,
        listing_id=listing_id,
        variant_id=variant_id,
        destination_country="US",
        quantity=quantity,
        method="CJPacket",
        cost_minor=cost,
        currency=currency,
    )


def capture(
    session: Session,
    listing_id: int,
    at: datetime,
    variant_id: int | None = None,
    origin: str | None = None,
    observed_for: date | None = None,
    **costs: int,
) -> int:
    """One freight response: a row per method it lists, all under one capture, as CJ writes.

    `observed_for` backdates it, as a CSV row may; the default is the capture's UTC date.
    """
    first, *rest = (
        {
            "listing_id": listing_id,
            "variant_id": variant_id,
            "origin_country": origin,
            "destination_country": "US",
            "method": method,
            "cost_minor": cost,
            "currency": "USD",
            "observed_for": observed_for or at.date(),
        }
        for method, cost in costs.items()
    )
    payload = observe(session, ShippingOption, CJ, at, **first).raw_payload_id
    session.add_all(ShippingOption(captured_at=at, raw_payload_id=payload, **row) for row in rest)
    session.flush()
    return payload


def lamp(session: Session, price: int = 2999) -> Product:
    """A product with one live USD store price and no supplier yet."""
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
        session,
        ListingSnapshot,
        SHOPIFY,
        listing_id=shop.id,
        values_hash="h",
        currency="USD",
        price_min_minor=price,
    )
    return product


def rate(session: Session, day: date, quote: str, value: str, source: str = "x") -> FxRate:
    at = datetime.combine(day + timedelta(days=1), datetime.min.time(), UTC)  # stored next day
    return observe(
        session,
        FxRate,
        FX,
        at,
        date=day,
        base="USD",
        quote=quote,
        source="frankfurter_blended" if source == "x" else source,
        rate=Decimal(value),
    )


@pytest.mark.db
def test_duty_not_set_is_incomplete_until_ddp_or_an_estimate(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, **FEES)
        product = lamp(session)
        cj = supplier_listing(session, product, 620)
        quote(session, cj, 485)
        session.commit()
        product_id = product.id

    body = calc(api, ws, product_id=product_id)
    assert (body["complete"], body["missing"]) == (False, ["duty_not_set"])
    assert (body["margin_minor"], body["margin_bps"], body["landed_cost_minor"]) == (None,) * 3
    assert (body["supplier_listing_id"], body["method"], body["price_minor"]) == (
        cj,
        "CJPacket",
        2999,
    )
    assert body["sources"]["price_minor"]["source"] == "shopify_stores"
    assert body["sources"]["unit_cost"]["source"] == "cj"
    assert datetime.fromisoformat(body["sources"]["freight"]["as_of"]) == DAY

    ddp = calc(api, ws, product_id=product_id, ddp=True)
    assert (ddp["complete"], ddp["missing"], ddp["duty_minor"]) == (True, [], 0)
    assert ddp["margin_minor"] == 2999 - 620 - 485 - 117 - 150

    estimate = calc(api, ws, product_id=product_id, duty_bps=2000)
    assert (estimate["complete"], estimate["margin_minor"], estimate["margin_bps"]) == (
        True,
        1503,
        5012,
    )
    assert estimate["estimates"] == ["duty_bps"]
    assert estimate["sources"]["duty_bps"] == {
        "source": "owner_estimate",
        "as_of": None,
        "raw_payload_id": None,
    }


@pytest.mark.db
def test_workspace_b_cannot_read_workspace_a_settings(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        a = workspace(session, duty_default_bps=2000, customs_fee_minor=99, **FEES)
        b = workspace(session)
        product = lamp(session)
        quote(session, supplier_listing(session, product, 620), 485)
        session.commit()
        product_id = product.id

    body = calc(api, a, product_id=product_id, customs_fee_minor=0)
    assert (body["complete"], body["margin_minor"]) == (True, 1503)
    assert body["sources"]["duty_bps"]["source"] == "settings"
    other = calc(api, b, product_id=product_id)
    assert other["missing"] == ["duty_not_set"]
    assert (other["payment_fee_minor"], other["returns_minor"], other["customs_fee_minor"]) == (
        0,
        0,
        0,
    )
    assert "duty_bps" not in other["sources"]


@pytest.mark.db
def test_fx_converts_at_the_observation_utc_date(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        cj = supplier_listing(session, product, 4000, "CNY")  # 40.00 CNY, captured 10-23 UTC
        quote(session, cj, 400, currency="EUR")
        day_rate = rate(session, date(2026, 10, 23), "CNY", "8")
        rate(session, date(2026, 10, 23), "CNY", "9", source="manual")  # the blend wins a tie
        rate(session, date(2026, 10, 24), "CNY", "7.2")  # later than the snapshot's UTC date
        rate(session, date(2026, 10, 18), "EUR", "0.8")  # five days back: too old
        session.commit()
        product_id, day_payload = product.id, day_rate.raw_payload_id

    body = calc(api, ws, product_id=product_id)
    assert body["goods_minor"] == 500
    assert body["sources"]["fx_unit_cost"]["raw_payload_id"] == day_payload
    assert datetime.fromisoformat(body["as_of"]) == DAY  # the oldest input, not the 10-24 rate
    assert (body["freight_minor"], body["missing"], body["margin_minor"]) == (
        None,
        ["fx_missing"],
        None,
    )

    with Session(db_engine) as session:
        rate(session, date(2026, 10, 19), "EUR", "0.8")  # four days back: bridges the gap
        session.commit()
    body = calc(api, ws, product_id=product_id)
    assert (body["freight_minor"], body["complete"]) == (500, True)
    assert datetime.fromisoformat(body["as_of"]) == datetime(2026, 10, 20, tzinfo=UTC)


@pytest.mark.db
def test_freight_matches_the_variant_and_quantity(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        cj = supplier_listing(session, product, 600)
        variants = [ListingVariant(listing_id=cj, external_id=key) for key in "AB"]
        session.add_all(variants)
        session.flush()
        for variant in variants:
            observe(
                session,
                VariantSnapshot,
                CJ,
                variant_id=variant.id,
                values_hash="h",
                currency="USD",
                price_minor=620,
            )
        quote(session, cj, 485)  # a null-variant quote can't cover a two-variant listing
        quote(session, cj, 500, variant_id=variants[0].id)
        single = supplier_listing(session, lamp(session), 620)
        only = ListingVariant(listing_id=single, external_id="only")
        session.add(only)
        session.flush()
        quote(session, single, 485, variant_id=only.id)
        session.commit()
        ids = {"product": product.id, "a": variants[0].id, "b": variants[1].id}
        ids |= {"single_product": session.get_one(Listing, single).product_id}

    def ask(**body: Any) -> Any:
        return calc(api, ws, product_id=ids["product"], supplier_listing_id=cj, **body)

    exact = ask(variant_id=ids["a"])
    assert (exact["freight_minor"], exact["goods_minor"], exact["complete"]) == (500, 620, True)
    assert ask(variant_id=ids["b"])["missing"] == ["freight_variant_mismatch"]
    assert ask()["missing"] == ["freight_variant_mismatch"]
    double = ask(variant_id=ids["a"], quantity=2, price_minor=5000)
    assert (double["goods_minor"], double["freight_minor"]) == (1240, None)
    assert double["missing"] == ["freight_missing"]  # never 2 x F(1)
    assert (double["estimates"], double["sources"]["price_minor"]["source"]) == (
        ["price_minor"],
        "owner_estimate",
    )
    assert ask(variant_id=ids["a"], quantity=2)["missing"] == ["price_missing", "freight_missing"]
    assert calc(api, ws, product_id=ids["single_product"])["freight_minor"] == 485


@pytest.mark.db
def test_an_unquoted_cheap_supplier_cannot_be_best(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        cheap = supplier_listing(session, product, 100)
        quote(session, supplier_listing(session, product, 700), 485)
        best = supplier_listing(session, product, 620)
        quote(session, best, 485)
        session.commit()
        product_id = product.id

    body = calc(api, ws, product_id=product_id)
    assert (body["supplier_listing_id"], body["complete"]) == (best, True)
    chosen = calc(api, ws, product_id=product_id, supplier_listing_id=cheap)
    assert (chosen["missing"], chosen["margin_minor"]) == (["freight_missing"], None)


@pytest.mark.db
def test_unknown_inputs_are_not_found(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        product, other = lamp(session), lamp(session)
        cj = supplier_listing(session, other, 620)
        merged = Product(name="Merged", merged_into_id=product.id)
        session.add(merged)
        session.commit()
        ids = {"product": product.id, "merged": merged.id}

    calc(api, ws, 404, product_id=uuid4())
    calc(api, ws, 404, product_id=ids["merged"])
    calc(api, ws, 404, product_id=ids["product"], supplier_listing_id=cj)
    calc(api, ws, 404, product_id=ids["product"], variant_id=1)
    none = calc(api, ws, product_id=ids["product"])
    assert none["supplier_listing_id"] is None
    assert none["missing"] == ["supplier_cost_missing", "freight_missing", "duty_not_set"]
    # No store price stands in at quantity 2, so only settings feed it: nothing observed.
    assert calc(api, ws, product_id=ids["product"], quantity=2)["as_of"] is None


@pytest.mark.db
def test_a_method_the_newest_capture_drops_is_never_priced(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0, **FEES)
        product = lamp(session)
        cj = supplier_listing(session, product, 620)
        capture(session, cj, DAY - timedelta(days=29), A=300, B=500)
        capture(session, cj, DAY, B=500)
        capture(session, cj, DAY - timedelta(hours=1), origin="US", USW=900)  # its own origin
        single = supplier_listing(session, lamp(session), 620)
        only = ListingVariant(listing_id=single, external_id="only")
        session.add(only)
        session.flush()
        capture(session, single, DAY - timedelta(days=29), manual=200)  # null variant
        capture(session, single, DAY, only.id, B=500)  # the same question, asked later
        session.commit()
        product_id, single_product = product.id, session.get_one(Listing, single).product_id

    body = calc(api, ws, product_id=product_id)
    assert (body["method"], body["freight_minor"], body["complete"]) == ("B", 500, True)
    assert body["margin_minor"] == 2999 - 620 - 500 - 117 - 150
    assert datetime.fromisoformat(body["sources"]["freight"]["as_of"]) == DAY
    dropped = calc(api, ws, product_id=product_id, method="A")
    assert (dropped["freight_minor"], dropped["complete"], dropped["missing"]) == (
        None,
        False,
        ["freight_missing"],
    )
    assert calc(api, ws, product_id=product_id, method="USW")["freight_minor"] == 900
    assert calc(api, ws, product_id=single_product)["method"] == "B"


@pytest.mark.db
def test_a_capture_tie_goes_to_the_later_raw_payload(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        dropped, added = (supplier_listing(session, product, 620) for _ in range(2))
        capture(session, dropped, DAY, A=300, B=500)
        capture(session, dropped, DAY, B=500)  # same captured_at, later raw payload
        capture(session, added, DAY, B=500)
        capture(session, added, DAY, A=300, B=500)
        session.commit()
        product_id = product.id

    def method(listing: int, **body: Any) -> Any:
        found = calc(api, ws, product_id=product_id, supplier_listing_id=listing, **body)
        return found["method"], found["missing"]

    assert method(dropped) == ("B", [])
    assert method(dropped, method="A") == (None, ["freight_missing"])
    assert method(added) == ("A", [])


@pytest.mark.db
def test_ddp_drops_unused_estimates_and_amounts_past_bigint_are_named(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, customs_fee_minor=99, **FEES)
        product = lamp(session)
        quote(session, supplier_listing(session, product, 620), 485)
        session.commit()
        product_id = product.id

    ddp = calc(api, ws, product_id=product_id, ddp=True, duty_bps=2500, returns_bps=0)
    assert (ddp["complete"], ddp["estimates"], ddp["customs_fee_minor"]) == (
        True,
        ["returns_bps"],
        0,
    )
    assert {"duty_bps", "customs_fee_minor"}.isdisjoint(ddp["sources"])
    top = 2**63 - 1
    huge = calc(
        api,
        ws,
        product_id=product_id,
        ddp=True,
        price_minor=top,
        payment_fee_bps=10000,
        payment_fee_fixed_minor=top,
    )
    assert (huge["payment_fee_minor"], huge["margin_minor"], huge["missing"]) == (
        None,
        None,
        ["amount_out_of_range"],
    )


@pytest.mark.db
def test_xr23_an_origin_whose_newest_answer_is_empty_is_not_priced(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0, **FEES)
        product = lamp(session)
        cj = supplier_listing(session, product, 620)
        variant = ListingVariant(listing_id=cj, external_id="vid-1")
        session.add(variant)
        session.flush()
        capture(session, cj, DAY - timedelta(days=29), variant.id, "CN", CJPacket=500)
        capture(session, cj, DAY - timedelta(days=29), variant.id, "US", USPS=300)
        capture(session, cj, DAY, variant.id, "CN", CJPacket=500)
        # Day 30's US answer is `data: []`: CJ keeps the raw capture and writes no row.
        run = CollectorRun(source_id=CJ, trigger="manual", status="success")
        session.add(run)
        session.flush()
        session.add(
            RawPayload(
                source_id=CJ,
                run_id=run.id,
                captured_at=DAY,
                request={
                    "endpoint": "/logistic/freightCalculate",
                    "startCountryCode": "US",
                    "endCountryCode": "US",
                    "products": [{"vid": "vid-1", "quantity": 1}],
                },
                bytes=40,
                sha256=uuid4().hex * 2,
            )
        )
        session.commit()
        product_id = product.id

    body = calc(api, ws, product_id=product_id)
    assert (body["method"], body["freight_minor"], body["complete"]) == ("CJPacket", 500, True)
    assert body["margin_minor"] == 2999 - 620 - 500 - 117 - 150
    usps = calc(api, ws, product_id=product_id, method="USPS")
    assert (usps["freight_minor"], usps["missing"]) == (None, ["freight_missing"])


@pytest.mark.db
def test_the_newest_capture_prices_every_method_at_its_latest_parse(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        cj = supplier_listing(session, product, 620)
        payload = capture(session, cj, DAY, A=300, B=500)
        session.add_all(  # the same capture re-parsed with corrected costs
            ShippingOption(
                listing_id=cj,
                destination_country="US",
                method=method,
                cost_minor=cost,
                currency="USD",
                captured_at=DAY,
                observed_for=DAY.date(),
                raw_payload_id=payload,
                parser_version="2",
            )
            for method, cost in {"A": 350, "B": 550}.items()
        )
        session.commit()
        product_id = product.id

    body = calc(api, ws, product_id=product_id)
    assert (body["method"], body["freight_minor"], body["complete"]) == ("A", 350, True)
    assert calc(api, ws, product_id=product_id, method="B")["freight_minor"] == 550


@pytest.mark.db
def test_a_quote_from_before_the_newest_day_is_not_priced(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, duty_default_bps=0)
        product = lamp(session)
        cj = supplier_listing(session, product, 620)
        day_1 = DAY - timedelta(days=29)
        capture(session, cj, day_1, manual=200)  # a CSV quote with no origin
        capture(session, cj, DAY, origin="CN", CJPacket=500, ePacket=450)
        # A CSV backfill of day 1, imported after CJ's day-30 capture.
        capture(session, cj, DAY + timedelta(hours=1), None, "CN", day_1.date(), manual=100)
        paired = supplier_listing(session, lamp(session), 620)
        variants = [ListingVariant(listing_id=paired, external_id=key) for key in "AB"]
        session.add_all(variants)
        session.flush()
        capture(session, paired, DAY - timedelta(days=7), variants[0].id, "CN", CJPacket=400)
        capture(session, paired, DAY, variants[1].id, "CN", CJPacket=500)
        session.commit()
        product_id, older = product.id, variants[0].id
        paired_product = session.get_one(Listing, paired).product_id

    body = calc(api, ws, product_id=product_id)
    assert (body["method"], body["freight_minor"], body["complete"]) == ("ePacket", 450, True)
    assert calc(api, ws, product_id=product_id, method="manual")["missing"] == ["freight_missing"]
    each = calc(
        api, ws, product_id=paired_product, supplier_listing_id=paired, variant_id=older
    )  # each variant has its own newest day
    assert (each["method"], each["freight_minor"]) == ("CJPacket", 400)
