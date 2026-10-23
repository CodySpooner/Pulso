import json
from datetime import UTC, date
from typing import Any, Literal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, attributes

from pulso_core.models import (
    Listing,
    ListingSnapshot,
    RawPayload,
    Source,
    Store,
    VariantSnapshot,
)
from pulso_core.settings import Settings
from pulso_sources.framework import Response, current_fields
from pulso_sources.imports import commit_import, replay_import
from pulso_sources.shopify_stores.imports import ShopifyImportAdapter
from pulso_sources.shopify_stores.variants import VARIANT_WRITERS

from .conftest import FIXTURES, fixture
from .test_catalog import CATALOG, run

CONTEXT = {"store_domain": "first.test", "shop_id": "1", "currency": "USD"}


@pytest.fixture
def import_catalog(session: Session, settings: Settings, io_mock: Any) -> None:
    body = json.loads(fixture("normal").body or b"")
    variant = body["products"][0]["variants"][0]
    body["products"][0]["variants"].append({**variant, "id": 2, "sku": "SKU-2", "title": "Large"})
    io_mock.replies[CATALOG] = Response(json.dumps(body).encode(), 200)
    assert run(session, settings).error_code is None
    source = session.get_one(Source, 1)
    source.enabled = False
    source.config = {**source.config, "shopify_import": CONTEXT}
    session.commit()
    io_mock.calls.clear()


def test_csv_groups_existing_variants_reports_bad_row_and_replays_once(
    session: Session, settings: Settings, io_mock: Any, import_catalog: None
) -> None:
    body = (FIXTURES / "import.csv").read_bytes()
    result = commit_import(session, "shopify_stores", body, settings=settings)
    assert result.status == "success", result.error_message
    assert result.rows_inserted == 3 and result.http_requests == 0
    assert result.params["errors"] == [
        {"row": 4, "column": "price", "message": "Invalid money value"}
    ]
    payload = session.get_one(RawPayload, result.params["raw_payload_id"])
    listing = session.scalars(select(Listing).filter_by(store_id=1)).one()
    assert listing.external_id == "1:1"
    snapshot = session.scalars(select(ListingSnapshot).filter_by(raw_payload_id=payload.id)).one()
    assert (snapshot.price_min_minor, snapshot.price_max_minor) == (1999, 2999)
    assert snapshot.available is None
    variants = list(session.scalars(select(VariantSnapshot).filter_by(raw_payload_id=payload.id)))
    assert len(variants) == 2
    observations: list[ListingSnapshot | VariantSnapshot] = [snapshot, *variants]
    for row in observations:
        assert row.observed_for == date(2020, 1, 1)
        assert row.captured_at.replace(tzinfo=UTC) == payload.captured_at.replace(tzinfo=UTC)
        assert row.parser_version and row.raw_payload_id == payload.id
    for row in variants:
        assert row.available is None and row.inventory_quantity is None
        current = current_fields(
            session, VariantSnapshot, key={"variant_id": row.variant_id}, writers=VARIANT_WRITERS
        )
        assert current["price_minor"].price_minor == 2499  # historical import stays historical
    unchanged = commit_import(session, "shopify_stores", body + b"\n", settings=settings)
    assert unchanged.status == "success" and unchanged.rows_inserted == 0
    assert unchanged.rows_unchanged == 3
    assert not session.get_one(Source, 1).enabled and not io_mock.calls


@pytest.mark.parametrize("mode", ["csv", "json"])
def test_new_store_import_and_correction_keep_original_context(
    session: Session,
    settings: Settings,
    io_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    mode: Literal["csv", "json"],
) -> None:
    source = session.get_one(Source, 1)
    source.enabled = False
    context = {**CONTEXT, "store_domain": "import.test"}
    source.config = {"shopify_import": context}
    session.commit()
    body = fixture("normal").body or b""
    if mode == "csv":
        body = (
            b"store_domain,product_url,title,price,currency,product_id,variant_id\n"
            b"import.test,https://import.test/products/product-1,Fixture product 1,24.99,USD,1,1\n"
            b"import.test,https://import.test/products/product-1,Fixture product 1,3e1,USD,1,2\n"
        )
    result = commit_import(
        session, source.key, body, settings=settings, mode=mode, observed_for=date(2020, 1, 1)
    )
    assert result.status == "success", result.error_message
    payload = session.get_one(RawPayload, result.params["raw_payload_id"])
    assert payload.request["shopify_import"] == context
    listing = session.scalars(select(Listing)).one()
    assert session.get_one(Store, listing.store_id).domain == "import.test"
    assert listing.external_id == "1:1"
    rows = list(session.scalars(select(VariantSnapshot)))
    assert len(rows) == (2 if mode == "csv" else 1)
    row = rows[0]
    assert row.price_minor == 2499 and row.inventory_quantity is None
    assert row.observed_for == (date(2020, 1, 1) if mode == "json" else payload.captured_at.date())
    fields = current_fields(
        session, VariantSnapshot, key={"variant_id": row.variant_id}, writers=VARIANT_WRITERS
    )
    assert fields["price_minor"].raw_payload_id == payload.id
    assert "inventory_quantity" not in fields
    assert (
        commit_import(
            session, source.key, body, settings=settings, mode=mode, observed_for=date(2020, 1, 1)
        ).status
        == "skipped"
    )
    source.config = {"shopify_import": {**context, "currency": "EUR"}}
    session.commit()
    # SQLite drops timezone metadata; PostgreSQL returns the original aware capture.
    attributes.set_committed_value(payload, "captured_at", payload.captured_at.replace(tzinfo=UTC))
    monkeypatch.setattr(ShopifyImportAdapter, "parser_version", "shopify-import-2")
    corrected = replay_import(session, payload.id, settings=settings)
    assert corrected.status == "success", corrected.error_message
    assert corrected.rows_inserted == len(rows) + 1
    assert replay_import(session, payload.id, settings=settings).rows_inserted == 0
    assert {r.currency for r in session.scalars(select(VariantSnapshot))} == {"USD"}
    assert not source.enabled and not io_mock.calls


@pytest.mark.parametrize("problem", ["context", "currency", "duplicate", "price"])
def test_json_rejects_missing_context_and_malformed_catalogs(
    session: Session,
    settings: Settings,
    io_mock: Any,
    problem: str,
) -> None:
    source = session.get_one(Source, 1)
    source.config = {} if problem == "context" else {"shopify_import": CONTEXT}
    if problem == "currency":
        source.config = {"shopify_import": {**CONTEXT, "currency": "ZZZ"}}
    session.commit()
    body = json.loads(fixture("normal").body or b"")
    if problem == "duplicate":
        body["products"].append(body["products"][0])
    if problem == "price":
        body["products"][0]["variants"][0]["price"] = "bad"
    result = commit_import(
        session,
        source.key,
        json.dumps(body).encode(),
        settings=settings,
        mode="json",
        observed_for=date(2020, 1, 1),
    )
    assert result.status in {"failed", "partial"} and result.error_code
    assert session.scalar(select(func.count()).select_from(Listing)) == 0
    assert session.scalar(select(func.count()).select_from(VariantSnapshot)) == 0
    assert not io_mock.calls
