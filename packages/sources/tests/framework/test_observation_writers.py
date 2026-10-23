"""DEC-120 writers: disjoint owned fields, aware cutoffs and request predicates on PostgreSQL."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, Listing, ListingVariant, RawPayload, VariantSnapshot
from pulso_sources.cj.tracked import VARIANT_WRITERS as CJ_WRITERS
from pulso_sources.framework import Writer, append_observation, current_fields
from pulso_sources.shopify_stores.variants import VARIANT_WRITERS as SHOPIFY_WRITERS

AT = datetime(2026, 10, 22, tzinfo=UTC)
PRICE = Writer(RawPayload.request["endpoint"].as_string() == "/a", ("price_minor",))


@pytest.mark.parametrize(
    "writers,cutoff",
    [
        ((PRICE, PRICE), None),  # a field with two owners
        ((Writer(PRICE.captures, ("price",)),), None),  # not a column
        ((PRICE,), AT.replace(tzinfo=None)),  # not UTC-aware
    ],
)
def test_current_fields_rejects_ambiguous_reads(
    writers: Sequence[Writer], cutoff: datetime | None
) -> None:
    session = Mock(spec=Session)
    with pytest.raises(ValueError):
        current_fields(
            session,
            VariantSnapshot,
            key={"variant_id": 1},
            writers=writers,
            captured_before=cutoff,
        )
    session.scalar.assert_not_called()


@pytest.mark.db
@pytest.mark.parametrize(
    "writers,requests",
    [
        (
            SHOPIFY_WRITERS,
            [{"path": "/products.json?limit=250&page=1"}, {"path": "/products/a_b.js"}],
        ),
        (
            CJ_WRITERS,
            [{"endpoint": "/product/query"}, {"endpoint": "/product/stock/getInventoryByPid"}],
        ),
    ],
)
def test_alternating_writers_on_postgres(
    db_engine: Engine, writers: Sequence[Writer], requests: list[dict[str, Any]]
) -> None:
    with Session(db_engine) as session:
        run = CollectorRun(source_id=1, trigger="fixture")
        listing = Listing(
            source_id=1, external_id="fixture", url="https://example.test", title="Fixture"
        )
        session.add_all([run, listing])
        session.flush()
        variant = ListingVariant(listing_id=listing.id, external_id="fixture")
        session.add(variant)
        session.flush()

        def append(hour: int) -> bool:
            at = AT + timedelta(hours=hour)
            capture = RawPayload(
                source_id=1,
                run_id=run.id,
                captured_at=at,
                request=requests[hour % 2],
                bytes=0,
                sha256="a" * 64,
            )
            session.add(capture)
            session.flush()
            values = [{"price_minor": 100}, {"inventory_quantity": 7}][hour % 2]
            row = VariantSnapshot(
                variant_id=variant.id,
                raw_payload_id=capture.id,
                parser_version="1",
                captured_at=at,
                observed_for=at.date(),
                currency="USD",
                values_hash=str(hour % 2) * 64,
                **values,
            )
            return append_observation(session, row, writer=writers[hour % 2])

        assert [append(hour) for hour in range(4)] == [True, True, False, False]
        price, stock = session.scalars(select(VariantSnapshot).order_by(VariantSnapshot.id))
        key = {"variant_id": variant.id}
        current = current_fields(session, VariantSnapshot, key=key, writers=writers)
        assert current["price_minor"].id == price.id
        assert current["inventory_quantity"].id == stock.id
        as_of = current_fields(
            session, VariantSnapshot, key=key, writers=writers, captured_before=AT + timedelta(1)
        )
        assert {row.id for row in as_of.values()} == {price.id, stock.id}
        assert not current_fields(
            session, VariantSnapshot, key=key, writers=writers, captured_before=AT
        )
