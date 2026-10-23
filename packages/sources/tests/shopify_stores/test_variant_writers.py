"""P1-37 probe S2 (DEC-120): catalog and .js variant rows are change-only per writer."""

from datetime import UTC
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, VariantSnapshot
from pulso_core.settings import Settings
from pulso_sources.framework import current_fields
from pulso_sources.shopify_stores.variants import VARIANT_WRITERS

from .conftest import fixture
from .test_catalog import CATALOG, run
from .test_variants import JS, catalog, js_run  # noqa: F401


def history(session: Session) -> tuple[int, list[VariantSnapshot]]:
    variant = session.scalars(
        select(ListingVariant)
        .join(Listing)
        .where(Listing.store_id == 1, ListingVariant.external_id == "1")
    ).one()
    rows = session.scalars(
        select(VariantSnapshot).filter_by(variant_id=variant.id).order_by(VariantSnapshot.id)
    )
    return variant.id, list(rows)


@pytest.mark.usefixtures("catalog")
def test_alternating_unchanged_writers_keep_their_own_current_fields(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    js_run(session, settings)
    io_mock.replies[CATALOG] = fixture("normal")  # the same page served 200 again
    run(session, settings)
    js_run(session, settings)
    variant_id, rows = history(session)
    assert len(rows) == 2  # unchanged catalog and .js captures append nothing
    catalog_row, js_row = rows
    key = {"variant_id": variant_id}
    current = current_fields(session, VariantSnapshot, key=key, writers=VARIANT_WRITERS)
    assert {name: row.id for name, row in current.items()} == {
        "price_minor": catalog_row.id,
        "compare_at_minor": catalog_row.id,
        "available": catalog_row.id,
        "source_updated_at": catalog_row.id,
        "inventory_quantity": js_row.id,
        "inventory_management": js_row.id,
        "inventory_policy": js_row.id,
    }
    assert (catalog_row.price_minor, js_row.inventory_quantity) == (2499, 7)
    assert catalog_row.raw_payload_id != js_row.raw_payload_id
    cutoff = js_row.captured_at.replace(tzinfo=UTC)
    before_js = current_fields(
        session, VariantSnapshot, key=key, writers=VARIANT_WRITERS, captured_before=cutoff
    )
    assert before_js["price_minor"].id == catalog_row.id
    assert "inventory_quantity" not in before_js  # missing, never zero or carried back

    io_mock.replies[JS] = fixture("variant_no_inventory")  # inventory hidden later
    js_run(session, settings)
    _, rows = history(session)
    current = current_fields(session, VariantSnapshot, key=key, writers=VARIANT_WRITERS)
    assert current["inventory_quantity"].id == rows[-1].id != js_row.id
    assert current["inventory_quantity"].inventory_quantity is None  # explicit unknown wins
    assert current["price_minor"].id == catalog_row.id
