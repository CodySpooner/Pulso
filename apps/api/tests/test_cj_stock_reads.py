"""imp-565 (DEC-356, DEC-348 part b): the API readers take a CJ listing's price from its newest
price capture and its stock from its newest stock reading. CJ rows go through the real
TrackedAdapter.upsert (so CJAdapter.upsert for the price row) on fixture records only."""

from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.matching import listing_detail
from pulso_core.landed_cost_loader import STOCK_ENDPOINT
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    RawPayload,
    Workspace,
    WorkspaceSettings,
)
from pulso_sources.cj.tracked import (
    Detail,
    Stock,
    StockVariant,
    TrackedAdapter,
    Variant,
    Warehouse,
)

CJ, PID = 2, "fixture-product"  # the seeded CJ source id
NOW = datetime.now(UTC).replace(microsecond=0)
NO_OFFER = "No in-stock supplier offer yet."


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def get(api: TestClient, workspace_id: UUID, path: str, **query: Any) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.get(path, params=query)
    assert response.status_code == 200, response.text
    return response.json()


def capture(session: Session, at: datetime, record: Detail | Stock) -> int:
    """One tracked CJ capture of PID at `at`, written by the real writers; its payload id."""
    endpoint = "/product/query" if isinstance(record, Detail) else STOCK_ENDPOINT
    run = CollectorRun(source_id=CJ, trigger="fixture", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=CJ, run_id=run.id, captured_at=at, request={"endpoint": endpoint, "pid": PID},
        bytes=1, sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    adapter = TrackedAdapter()
    adapter.upsert(session, [record], payload, parser_version=adapter.parser_version)
    session.commit()
    return payload.id


def detail(price: str) -> Detail:
    variant = Variant(vid="fixture-variant", variantSellPrice=Decimal(price))
    return Detail(pid=PID, productNameEn="Sunset lamp", sellPrice=price, variants=[variant])


def stock(total: int | None) -> Stock:
    """A stock capture; None is a variant listing no warehouse: an unknown total."""
    found = None if total is None else [Warehouse(countryCode="CN", totalInventory=total)]
    return Stock(variantInventories=[StockVariant(vid="fixture-variant", inventory=found)])


def offer(session: Session, at: datetime, price: str = "7.40") -> tuple[UUID, UUID, int]:
    """A workspace and a product whose one CJ offer is first captured at `at`."""
    workspace, product = Workspace(name="Workspace"), Product(name="Sunset lamp")
    session.add_all([workspace, product])
    session.flush()
    session.add(WorkspaceSettings(workspace_id=workspace.id))
    priced = capture(session, at, detail(price))
    listing = session.scalars(select(Listing).filter_by(source_id=CJ, external_id=PID)).one()
    listing.product_id = product.id
    session.commit()
    return workspace.id, product.id, priced


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


@pytest.mark.db
def test_a_newest_stock_row_keeps_the_unit_cost_and_its_own_stock_trace(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws, product_id, priced = offer(session, NOW - timedelta(hours=4))
        listing_id = session.scalars(select(Listing.id).filter_by(external_id=PID)).one()
        for hours, total, held in ((3, 12, True), (2, 0, False), (1, None, True)):
            at = NOW - timedelta(hours=hours)
            stocked = capture(session, at, stock(total))
            newest = session.scalars(
                select(ListingSnapshot).order_by(ListingSnapshot.id.desc())
            ).first()
            assert newest is not None and newest.price_min_minor is None  # a stock-only row

            [row] = get(api, ws, f"/v1/products/{product_id}/suppliers")["rows"]
            assert (row["unit_cost_minor"], row["currency"]) == (740, "USD"), hours
            assert row["as_of"] == iso(NOW - timedelta(hours=4))  # the price row's
            assert row["in_stock"] is held, hours
            if total is None:  # the unknown total supersedes the stock-out (DEC-348)
                assert row["stock"]["value"] is None and row["stock"]["reason"]
            else:
                trace = row["stock"]
                assert (trace["value"], trace["as_of"], trace["raw_payload_id"]) == (
                    total, iso(at), stocked,
                )  # fmt: skip

            overview = get(api, ws, f"/v1/products/{product_id}/overview")
            cost = overview["best_supplier_cost_minor"]
            if held:
                assert (cost["value"], cost["raw_payload_id"], cost["platform"]) == (
                    740, priced, "cj",
                )  # fmt: skip
            else:
                assert cost == {"value": None, "reason": NO_OFFER}
            [item] = get(api, ws, "/v1/products")["items"]
            suppliers = item["supplier_count"]
            assert (suppliers["value"], suppliers["raw_payload_id"]) == (1, priced)

            price = listing_detail(session, listing_id).price
            assert price is not None and (price.min_minor, price.captured_at) == (
                740, NOW - timedelta(hours=4),
            )  # fmt: skip


@pytest.mark.db
def test_a_newest_row_with_both_fields_reads_as_before(api: TestClient, db_engine: Engine) -> None:
    """A listing whose newest row carries price and stock (a CSV or store-like capture) reads
    everything from that one row, as before DEC-356."""
    with Session(db_engine) as session:
        ws, product_id, _ = offer(session, NOW - timedelta(hours=2), "9.00")
        listing_id = session.scalars(select(Listing.id).filter_by(external_id=PID)).one()
        run = CollectorRun(source_id=CJ, trigger="manual", status="success")
        session.add(run)
        session.flush()
        payload = RawPayload(
            source_id=CJ, run_id=run.id, captured_at=NOW - timedelta(hours=1), request={},
            bytes=1, sha256=uuid4().hex * 2,
        )  # fmt: skip
        session.add(payload)
        session.flush()
        session.add(
            ListingSnapshot(
                listing_id=listing_id, captured_at=payload.captured_at, raw_payload_id=payload.id,
                observed_for=payload.captured_at.date(), values_hash="both", currency="USD",
                price_min_minor=650, stock=7,
            )
        )  # fmt: skip
        session.commit()
        at = iso(NOW - timedelta(hours=1))
        [row] = get(api, ws, f"/v1/products/{product_id}/suppliers")["rows"]
        assert (row["unit_cost_minor"], row["as_of"], row["in_stock"]) == (650, at, True)
        assert (row["stock"]["value"], row["stock"]["as_of"]) == (7, at)
        assert row["stock"]["raw_payload_id"] == payload.id
        cost = get(api, ws, f"/v1/products/{product_id}/overview")["best_supplier_cost_minor"]
        assert (cost["value"], cost["raw_payload_id"]) == (650, payload.id)
        price = listing_detail(session, listing_id).price
        assert price is not None and price.min_minor == 650


@pytest.mark.db
def test_pulse_reads_an_unknown_total_as_superseding_a_stock_out(
    api: TestClient, db_engine: Engine
) -> None:
    day = NOW.date() - timedelta(days=5)
    before = datetime.combine(day - timedelta(days=1), time(6), UTC)
    with Session(db_engine) as session:
        ws, product_id, _ = offer(session, before - timedelta(hours=1))
        capture(session, before, stock(0))  # sold out the day before
        unknown = capture(session, datetime.combine(day, time(7), UTC), stock(None))
    moves = get(api, ws, "/v1/pulse", date=day.isoformat())["sections"]["suppliers"]["items"]
    [move] = moves
    assert (move["product"]["id"], move["was_in_stock"], move["in_stock"]) == (
        str(product_id), False, True,
    )  # fmt: skip
    assert (move["raw_payload_id"], move["new_price_minor"]) == (unknown, None)
