import json
from datetime import UTC, date
from typing import Any, Literal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, attributes

from pulso_core.models import (
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    Source,
    Store,
    VariantSnapshot,
)
from pulso_core.settings import Settings
from pulso_sources import shopify_stores
from pulso_sources.framework import Response, current_fields
from pulso_sources.imports import commit_import, parse_csv, replay_import
from pulso_sources.shopify_stores.imports import ShopifyImportAdapter
from pulso_sources.shopify_stores.records import parse
from pulso_sources.shopify_stores.variants import VARIANT_WRITERS

from .conftest import FIXTURES, fixture
from .test_catalog import CATALOG, run

CONTEXT = {"store_domain": "first.test", "shop_id": "1", "currency": "USD"}
URL = "https://first.test/products/product-1"
HEADER = (
    "store_domain,product_url,title,price,currency,compare_at_price,available,product_id,variant_id"
)


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
        line = "import.test,https://import.test/products/product-1,Fixture product 1"
        body = f"{HEADER}\n{line},24.99,USD,,,1,1\n{line},3e1,USD,,,1,2\n".encode()
    observed_for = date(2020, 1, 1) if mode == "json" else None  # CSV rows carry dates (DEC-160)
    result = commit_import(
        session, source.key, body, settings=settings, mode=mode, observed_for=observed_for
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
            session, source.key, body, settings=settings, mode=mode, observed_for=observed_for
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


# P1-51 regressions: the P1-50 probes of P1-07c abb0c4b, inverted (DEC-162).
def utc(value: Any) -> Any:
    return value and value.replace(tzinfo=UTC)


def live_catalog(io_mock: Any, *variants: dict[str, Any], products: int = 1) -> None:
    body = json.loads(fixture("normal").body or b"")
    base = body["products"][0]
    base["variants"] = [{**base["variants"][0], **v} for v in variants] or base["variants"]
    body["products"] = [
        {**base, "id": i, "handle": f"product-{i}", "title": f"Live title {i}"}
        for i in range(1, products + 1)
    ]
    io_mock.replies[CATALOG] = Response(json.dumps(body).encode(), 200)


def crawl(session: Session, settings: Settings) -> None:
    session.get_one(Source, 1).enabled = True
    session.commit()
    assert run(session, settings).error_code is None


def importing(
    session: Session, settings: Settings, body: bytes, context: Any = CONTEXT, **kw: Any
) -> Any:
    source = session.get_one(Source, 1)
    source.enabled, source.config = False, {**source.config, "shopify_import": context}
    session.commit()
    return commit_import(session, "shopify_stores", body, settings=settings, **kw)


def mine(session: Session) -> Listing:
    return session.scalars(select(Listing).filter_by(store_id=1, external_id="1:1")).one()


def current(session: Session, external_id: str = "1") -> dict[str, Any]:
    variant = session.scalars(
        select(ListingVariant).filter_by(listing_id=mine(session).id, external_id=external_id)
    ).one()
    fields = current_fields(
        session, VariantSnapshot, key={"variant_id": variant.id}, writers=VARIANT_WRITERS
    )
    out = {k: getattr(row, k) for k, row in fields.items() if k != "inventory_quantity"}
    return {**out, "raw": fields["price_minor"].raw_payload_id, "title": variant.title}


def payload_rows(session: Session, model: Any, result: Any) -> int:
    raw = result.params.get("raw_payload_id")
    return (
        session.scalar(select(func.count()).select_from(model).filter_by(raw_payload_id=raw)) or 0
    )


def js_panel(session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Handles the variants_js plan would request for first.test (planning only, no HTTP)."""
    panels: dict[str, list[str]] = {}

    def catalog(self: Any, store: Store, panel: Any = None) -> Any:
        panels[store.domain] = [listing.handle for listing in panel or []]
        return iter(())

    with monkeypatch.context() as patch:
        patch.setattr(shopify_stores.ShopifyAdapter, "catalog", catalog)
        shopify_stores.plan(
            session, session.get_one(Source, 1), settings=settings, job="variants_js"
        )
    return panels.get("first.test", [])


@pytest.mark.parametrize("mode", ["csv", "json"])
def test_backdated_import_never_relists_or_rewrites_current_state(
    session: Session,
    settings: Settings,
    io_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    live_catalog(io_mock)
    crawl(session, settings)
    io_mock.replies[CATALOG] = fixture("empty_catalog")
    crawl(session, settings)
    listing = mine(session)
    variant = session.scalars(select(ListingVariant).filter_by(listing_id=listing.id)).one()

    def state() -> tuple[Any, ...]:
        session.refresh(listing)
        session.refresh(variant)
        return (
            *(utc(listing.last_seen_at), utc(listing.delisted_at), listing.title, listing.url),
            *(utc(variant.last_seen_at), utc(variant.delisted_at), variant.title),
        )

    before, read = state(), current(session)
    assert before[1] is not None
    kw: dict[str, Any] = {}
    body = (
        f"{HEADER},variant_title,observed_for\n"
        f"first.test,{URL},Old 2020 title,9.99,USD,,true,1,1,Old variant,2020-01-01\n"
    ).encode()
    if mode == "json":
        data = json.loads(fixture("normal").body or b"")
        data["products"][0]["title"] = "Old 2020 title"
        data["products"][0]["variants"][0].update(title="Old variant", price="9.99")
        body, kw = json.dumps(data).encode(), {"mode": mode, "observed_for": date(2020, 1, 1)}
    assert importing(session, settings, body, **kw).status == "success"
    assert importing(session, settings, body + b"\n", **kw).rows_inserted == 0
    assert state() == before and current(session) == read  # 2020 rows stay history
    assert js_panel(session, settings, monkeypatch) == []
    crawl(session, settings)  # the next complete catalog keeps the original delisting time
    assert state() == before


def test_current_dated_import_refreshes_text_but_is_not_a_sighting(
    session: Session, settings: Settings, io_mock: Any, import_catalog: None
) -> None:
    listing = mine(session)
    seen = utc(listing.last_seen_at)
    body = (
        f"{HEADER},variant_title\n"
        f"first.test,{URL},New title,24.99,USD,29.99,true,1,1,Renamed\n"
        f"first.test,{URL},New title,24.99,USD,29.99,true,1,2,Large\n"
    ).encode()
    assert importing(session, settings, body).status == "success"
    session.refresh(listing)
    assert (listing.title, utc(listing.last_seen_at)) == ("New title", seen)
    assert current(session)["title"] == "Renamed"


def test_missing_owned_headers_fail_before_storage(
    session: Session, settings: Settings, io_mock: Any, import_catalog: None
) -> None:
    before = current(session)
    body = (
        "store_domain,product_url,title,price,currency,product_id,variant_id\n"
        f"first.test,{URL},Fixture product 1,24.99,USD,1,1\n"
    ).encode()
    with pytest.raises(ValueError, match="compare_at_price, available"):
        parse_csv("shopify_stores", body)
    result = importing(session, settings, body)
    assert result.status == "failed" and "raw_payload_id" not in (result.params or {})
    assert current(session) == before


@pytest.mark.parametrize("title_column", [True, False], ids=["blank_title", "absent_title"])
def test_blank_owned_cells_have_the_documented_meaning(
    session: Session, settings: Settings, io_mock: Any, import_catalog: None, title_column: bool
) -> None:
    cell = "," if title_column else ""
    body = (
        f"{HEADER}{',variant_title' if title_column else ''}\n"
        + "".join(f"first.test,{URL},Fixture product 1,24.99,USD,,,1,{v}{cell}\n" for v in "12")
    ).encode()
    result = importing(session, settings, body)
    assert result.status == "success"
    # Blank compare-at is no compare-at, blank available is unknown, CSV has no updated_at.
    assert current(session) == {
        "price_minor": 2499,
        "compare_at_minor": None,
        "available": None,
        "source_updated_at": None,
        "raw": result.params["raw_payload_id"],
        "title": "Default",  # blank or absent text keeps the stored variant title
    }


def test_partial_variant_file_keeps_the_listing_aggregate(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    live_catalog(io_mock, {}, {"id": 2, "sku": "SKU-2", "title": "Large", "price": "34.99"})
    crawl(session, settings)
    body = f"{HEADER}\nfirst.test,{URL},Live title 1,34.99,USD,39.99,true,1,2\n".encode()
    result = importing(session, settings, body)
    assert result.status == "success"
    assert payload_rows(session, ListingSnapshot, result) == 0
    assert payload_rows(session, VariantSnapshot, result) == 1
    latest = session.scalars(
        select(ListingSnapshot)
        .filter_by(listing_id=mine(session).id)
        .order_by(ListingSnapshot.observed_for.desc(), ListingSnapshot.captured_at.desc())
    ).first()
    assert latest is not None and (latest.price_min_minor, latest.price_max_minor) == (2499, 3499)


def test_context_currency_must_match_the_qualified_store(
    session: Session, settings: Settings, io_mock: Any, import_catalog: None
) -> None:
    before = current(session)
    body = f"{HEADER}\nfirst.test,{URL},Fixture product 1,24.99,EUR,29.99,true,1,1\n".encode()
    result = importing(session, settings, body, context={**CONTEXT, "currency": "EUR"})
    assert result.status in {"failed", "partial"} and result.error_code
    assert payload_rows(session, ListingSnapshot, result) == 0
    assert payload_rows(session, VariantSnapshot, result) == 0
    assert current(session) == before and session.get_one(Store, 1).currency == "USD"


@pytest.mark.parametrize("field,absent", [("available", False), ("title", False), ("title", True)])
def test_live_catalog_rejects_unknown_available_and_title(field: str, absent: bool) -> None:
    data = json.loads(fixture("normal").body or b"")
    variant = data["products"][0]["variants"][0]
    variant.pop(field) if absent else variant.update({field: None})
    with pytest.raises(ValueError):
        parse(json.dumps(data).encode())


def test_imports_do_not_reorder_the_js_panel(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_catalog(io_mock, products=2)
    crawl(session, settings)
    small = settings.model_copy(update={"shopify_js_panel_size": 1})
    assert js_panel(session, small, monkeypatch) == ["product-1"]
    body = f"{HEADER},observed_for\nfirst.test,{URL},Live title 1,24.99,USD,,true,1,1,2020-01-01\n"
    assert importing(session, settings, body.encode()).status == "success"
    assert js_panel(session, small, monkeypatch) == ["product-1"]


# imp-150 (XR-2): ID-less rows never resolve to a delisted listing or variant.
SKU_HEADER = (
    "store_domain,product_url,title,price,currency,compare_at_price,available,sku,product_id"
)


def adapter_errors(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Exception texts from the import adapter; runs record only the exception type."""
    errors: list[str] = []
    upsert = ShopifyImportAdapter.upsert

    def spy(self: ShopifyImportAdapter, *args: Any, **kw: Any) -> Any:
        try:
            return upsert(self, *args, **kw)
        except Exception as exc:
            errors.append(str(exc))
            raise

    monkeypatch.setattr(ShopifyImportAdapter, "upsert", spy)
    return errors


def delisted_product(session: Session, settings: Settings, io_mock: Any) -> Listing:
    """Product A (product-1, SKU-1) is deleted; a twin with its handle and SKU is not crawled."""
    live_catalog(io_mock)
    crawl(session, settings)
    io_mock.replies[CATALOG] = fixture("empty_catalog")
    crawl(session, settings)
    listing = mine(session)
    assert listing.delisted_at is not None
    return listing


def test_handle_only_row_never_resolves_to_a_delisted_listing(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing = delisted_product(session, settings, io_mock)
    errors = adapter_errors(monkeypatch)
    body = f"{SKU_HEADER}\nfirst.test,{URL},Twin title,24.00,USD,,,SKU-1,\n".encode()
    result = importing(session, settings, body)
    assert (result.status, result.error_code) == ("partial", "ValueError")
    assert errors == ["Unknown handle requires a Shopify product_id"]
    assert payload_rows(session, ListingSnapshot, result) == 0
    assert payload_rows(session, VariantSnapshot, result) == 0
    session.refresh(listing)
    assert listing.title == "Live title 1"


def test_sku_only_row_never_resolves_to_a_delisted_variant(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    live_catalog(io_mock, {}, {"id": 2, "sku": "SKU-2", "title": "Large"})
    crawl(session, settings)
    variant = session.scalars(select(ListingVariant).filter_by(external_id="2")).one()
    variant.delisted_at = variant.last_seen_at  # no crawl delists variants yet; imports still must
    session.commit()
    errors = adapter_errors(monkeypatch)
    body = f"{SKU_HEADER}\nfirst.test,{URL},Live title 1,24.00,USD,,,SKU-2,\n".encode()
    result = importing(session, settings, body)
    assert (result.status, result.error_code) == ("partial", "ValueError")
    assert errors == ["Unknown variant requires a Shopify variant_id"]
    assert payload_rows(session, ListingSnapshot, result) == 0
    assert payload_rows(session, VariantSnapshot, result) == 0


def test_explicit_product_id_still_records_history_for_a_delisted_listing(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    listing = delisted_product(session, settings, io_mock)
    body = f"{SKU_HEADER}\nfirst.test,{URL},Twin title,24.00,USD,,,SKU-1,1\n".encode()
    result = importing(session, settings, body)
    assert result.status == "success"
    assert payload_rows(session, VariantSnapshot, result) == 1
    assert current(session)["price_minor"] == 2400
    session.refresh(listing)
    assert listing.delisted_at is not None
