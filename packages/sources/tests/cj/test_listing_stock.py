"""imp-545 (DEC-348): a tracked run's stock reaches the listing readers and the R-23 alerts."""

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.alerts import evaluate, latest
from pulso_core.landed_cost_loader import stocked, unit_cost
from pulso_core.models import (
    Alert,
    Listing,
    ListingSnapshot,
    ListingVariant,
    Product,
    ProductTest,
    Source,
    VariantSnapshot,
    Workspace,
)
from pulso_sources import storage
from pulso_sources.cj.budget import record_points

from .test_cj import fixture
from .test_variant_writers import tracked_run


@pytest.fixture
def db(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    objects: dict[str, bytes] = {}
    client = Mock()
    client.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", Mock())
    with Session(db_engine, expire_on_commit=False) as session:
        record_points(session.get_one(Source, 2), fixture("list_v2"), datetime.now(UTC))
        session.commit()
        yield session


def stock(a: int, b: int) -> bytes:
    """The stock fixture with both variants known: one CN warehouse each."""
    body = json.loads(fixture("stock"))
    for variant, total in zip(body["data"]["variantInventories"], (a, b), strict=True):
        variant["inventory"] = [{"countryCode": "CN", "totalInventory": total}]
    return json.dumps(body).encode()


def counts(session: Session) -> tuple[int | None, int | None]:
    return session.scalar(select(func.count()).select_from(ListingSnapshot)), session.scalar(
        select(func.count()).select_from(VariantSnapshot)
    )


@pytest.mark.db
def test_a_stock_out_fires_r23_once_and_the_listing_keeps_its_cost(db: Session) -> None:
    tracked_run(db, stock(12, 3))
    listing = db.scalars(select(Listing)).one()
    newest = db.scalars(select(ListingSnapshot).order_by(ListingSnapshot.id.desc())).first()
    assert newest is not None and (newest.stock, newest.price_min_minor) == (15, None)
    product = Product(name="Synthetic CJ product")
    workspace = Workspace(name="Workspace")
    db.add_all([product, workspace])
    db.flush()
    listing.product_id = product.id
    db.add(ProductTest(workspace_id=workspace.id, product_id=product.id, stage="testing"))
    evaluate(db, workspace.id, datetime.now(UTC))  # R-23's reference: in stock
    assert stocked(db, listing.id)

    tracked_run(db, stock(0, 0))  # the next run: every variant sold out
    evaluate(db, workspace.id, datetime.now(UTC))
    [alert] = db.scalars(select(Alert))
    assert (alert.type, alert.entity_id) == ("supplier_stock_out", str(listing.id))
    assert alert.payload["new"]["value"] is False
    assert not stocked(db, listing.id)
    cost = unit_cost(db, listing.id, None)  # the stock row is newest; the detail price holds
    assert cost is not None and cost.minor == 125
    variant = db.scalars(select(ListingVariant).filter_by(external_id="fixture-variant-a")).one()
    chosen = unit_cost(db, listing.id, variant.id)  # was None on main (DEC-343's related bug)
    assert chosen is not None and chosen.minor == 125

    before = counts(db)
    tracked_run(db, stock(0, 0))  # the same payloads again: change-only per writer
    assert counts(db) == before
    evaluate(db, workspace.id, datetime.now(UTC))
    assert db.scalar(select(func.count()).select_from(Alert)) == 1


@pytest.mark.db
def test_an_unknown_variant_makes_the_listing_total_unknown(db: Session) -> None:
    tracked_run(db, stock(0, 0))
    listing = db.scalars(select(Listing)).one()
    assert not stocked(db, listing.id)
    tracked_run(db)  # the fixture: variant b lists no warehouse, so its stock is unknown
    rows = db.scalars(select(ListingSnapshot.stock).order_by(ListingSnapshot.id)).all()
    assert rows == [None, 0, None]  # price, sold out, unknown: no carried level
    assert stocked(db, listing.id)  # unknown supersedes the stock-out (DEC-120)
    row = latest(db, "supplier_stock_out", listing.id, datetime.now(UTC))  # and in R-23's read
    assert row is not None and (row.available, row.stock) == (None, None)
