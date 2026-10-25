from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
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
from pulso_core.db import Base
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
    row = model(captured_at=at, observed_for=at.date(), raw_payload_id=payload.id, **values)
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
