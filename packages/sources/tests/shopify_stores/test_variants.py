import json
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    Source,
    Store,
    VariantSnapshot,
)
from pulso_core.settings import Settings
from pulso_sources import framework, shopify_stores
from pulso_sources.framework import Response, enqueue_run
from pulso_workers import tasks

from .conftest import fixture
from .test_catalog import CATALOG, run
from .test_registered_plan import registered  # noqa: F401

JS = "https://first.test/products/product-1.js"


def js_run(session: Session, settings: Settings) -> CollectorRun:
    queued = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    adapter, targets, finalize = shopify_stores.plan(
        session, session.get_one(Source, 1), settings=settings, job="variants_js"
    )
    result = framework.execute_run(
        session,
        queued.id,
        adapter,
        targets,
        settings=settings.model_copy(update={"collector_max_retries": 0}),
        request_hook=adapter.request_hook,
    )
    finalize(session, result)
    return result


@pytest.fixture
def catalog(session: Session, settings: Settings, io_mock: Any) -> None:
    run(session, settings)
    for domain in ("first.test", "second.test"):
        io_mock.replies[JS.replace("first.test", domain)] = fixture("variant_inventory")


def test_inventory_snapshots_replay_and_conditional_cache(
    session: Session,
    settings: Settings,
    io_mock: Any,
    catalog: None,
) -> None:
    crawl_at = session.get_one(Store, 1).last_crawled_at
    result = js_run(session, settings)
    assert result.error_code is None, (result.error_code, result.error_message)
    row = session.scalars(
        select(VariantSnapshot).where(VariantSnapshot.inventory_quantity == 7)
    ).first()
    assert row is not None and row.price_minor == 2499 and row.compare_at_minor == 2999
    assert (row.inventory_management, row.inventory_policy) == ("shopify", "deny")
    variant = session.get_one(ListingVariant, row.variant_id)
    assert variant.barcode == "0012345678905"
    payload = session.get_one(RawPayload, row.raw_payload_id)
    payload.captured_at = payload.captured_at.replace(tzinfo=UTC)
    adapter = shopify_stores.ShopifyAdapter(settings)
    assert (
        adapter.upsert(
            session,
            adapter.parse(fixture("variant_inventory").body or b""),
            payload,
            parser_version=adapter.parser_version,
        ).inserted
        == 0
    )
    session.commit()
    count = session.scalar(select(func.count()).select_from(VariantSnapshot))
    io_mock.calls.clear()
    for domain in ("first.test", "second.test"):
        io_mock.replies[JS.replace("first.test", domain)] = fixture("not_modified")
    assert js_run(session, settings).error_code is None
    assert session.scalar(select(func.count()).select_from(VariantSnapshot)) == count
    assert all(
        h.get("If-none-match") == '"js-v1"' for u, _, h in io_mock.calls if u.endswith(".js")
    )
    assert not any(u.endswith("robots.txt") for u, _, _ in io_mock.calls)
    assert session.get_one(Store, 1).last_crawled_at == crawl_at


@pytest.mark.parametrize("inventory", [None, 0, -2, 8])
def test_present_and_missing_inventory(
    session: Session, settings: Settings, io_mock: Any, catalog: None, inventory: int | None
) -> None:
    js_run(session, settings)
    body = json.loads(fixture("variant_no_inventory").body or b"")
    if inventory is not None:
        body["variants"][0]["inventory_quantity"] = inventory
    io_mock.replies[JS] = Response(json.dumps(body).encode(), 200)
    result = js_run(session, settings)
    assert result.error_code is None, (result.error_code, result.error_message)
    row = session.scalars(
        select(VariantSnapshot)
        .join(ListingVariant)
        .join(Listing)
        .where(Listing.store_id == 1)
        .order_by(VariantSnapshot.id.desc())
    ).first()
    assert row is not None and row.inventory_quantity == inventory
    assert (
        session.scalar(
            select(func.count())
            .select_from(VariantSnapshot)
            .where(VariantSnapshot.inventory_quantity == 7)
        )
        == 2
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("inventory_quantity", True),
        ("inventory_quantity", "7"),
        ("inventory_quantity", 1.5),
        ("inventory_quantity", 2**63),
        ("price", "2499"),
        ("price", 24.99),
        ("price", True),
    ],
)
def test_invalid_js_values_are_rejected(settings: Settings, field: str, value: Any) -> None:
    body = json.loads(fixture("variant_inventory").body or b"")
    body["variants"][0][field] = value
    with pytest.raises(ValueError):
        shopify_stores.ShopifyAdapter(settings).parse(json.dumps(body).encode())


@pytest.mark.parametrize("size", [1, 10])
def test_panel_cap_latest_products_and_shared_spacing(
    session: Session,
    settings: Settings,
    io_mock: Any,
    size: int,
) -> None:
    body = json.loads(fixture("page_1").body or b"")
    body["products"] = body["products"][:12]
    for product in body["products"]:
        product["updated_at"] = f"2026-10-{product['id']:02d}T00:00:00Z"
    io_mock.replies[CATALOG] = Response(json.dumps(body).encode(), 200)
    run(session, settings)
    for product in body["products"]:
        js = json.loads(fixture("variant_inventory").body or b"")
        js["id"], js["handle"] = product["id"], product["handle"]
        js["variants"][0]["id"] = product["variants"][0]["id"]
        io_mock.replies[f"https://first.test/products/{product['handle']}.js"] = Response(
            json.dumps(js).encode(), 200
        )
    io_mock.replies[JS.replace("first.test", "second.test")] = fixture("variant_no_inventory")
    assert (
        js_run(session, settings.model_copy(update={"shopify_js_panel_size": size})).error_code
        is None
    )
    urls = [u for u, _, _ in io_mock.calls if "first.test/products/" in u]
    assert urls == [f"https://first.test/products/product-{i}.js" for i in range(12, 12 - size, -1)]
    calls = io_mock.calls
    assert all(b[1] - a[1] >= 2 for a, b in zip(calls, calls[1:], strict=False))
    for domain in ("first.test", "second.test"):
        times = [t for u, t, _ in calls if domain in u]
        assert all(b - a >= 10 - 1e-6 for a, b in zip(times, times[1:], strict=False))
    assert all(h["User-agent"] == settings.collector_user_agent for _, _, h in calls)
    assert session.scalar(select(func.count()).select_from(ListingSnapshot)) == 13


@pytest.mark.parametrize("failure", ["robots", "304", "503", "430", "wrong_product"])
def test_js_failure_preserves_catalog_and_never_delists(
    session: Session,
    settings: Settings,
    io_mock: Any,
    catalog: None,
    failure: str,
) -> None:
    before = session.get_one(Store, 1).last_crawled_at
    if failure == "robots":
        for payload in session.scalars(select(RawPayload)):
            payload.captured_at = datetime(2026, 1, 1, tzinfo=UTC)
        session.commit()
        io_mock.replies["https://first.test/robots.txt"] = Response(
            b"User-agent: *\nDisallow: /products/*.js", 200
        )
    elif failure == "wrong_product":
        body = json.loads(fixture("variant_inventory").body or b"")
        body["id"] = 999
        io_mock.replies[JS] = Response(json.dumps(body).encode(), 200, etag='"bad"')
    else:
        io_mock.replies[JS] = Response(None, int(failure))
    result = js_run(session, settings)
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_variants_js", "first.test")).status
        != "success"
    )
    assert session.get_one(Store, 1).last_crawled_at == before
    assert all(row.delisted_at is None for row in session.scalars(select(Listing)))
    assert [u for u, _, _ in io_mock.calls].count(JS) == (0 if failure == "robots" else 1)
    if failure == "430":
        assert not session.get_one(Source, 1).enabled
        assert not any("second.test/products/" in u for u, _, _ in io_mock.calls)
    if failure in {"wrong_product", "503"}:
        io_mock.calls.clear()
        io_mock.replies[JS] = fixture("variant_inventory")
        assert js_run(session, settings).error_code is None
        assert "If-none-match" not in next(h for u, _, h in io_mock.calls if u == JS)


@pytest.mark.parametrize("guard", ["disabled", "worktree", "live_off", "allowed"])
@pytest.mark.usefixtures("registered")
def test_registered_js_plan_and_guards(
    session: Session,
    settings: Settings,
    io_mock: Any,
    catalog: None,
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
) -> None:
    source = session.get_one(Source, 1)
    source.enabled = False
    session.commit()
    plan = tasks.PLANS[source.key](session, source, "variants_js")
    assert not source.enabled and plan.collector_max_retries == 0
    if guard != "disabled":
        source.enabled = True
        session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: guard == "worktree")
    monkeypatch.setattr(
        tasks,
        "get_settings",
        lambda: settings.model_copy(update={"collectors_live": guard != "live_off"}),
    )
    io_mock.calls.clear()
    queued = enqueue_run(
        session,
        source_id=1,
        trigger="manual",
        publish=lambda _: None,
        slot_key="variants_js:2026-10-23",
    )
    tasks.collect_run(queued.id)
    session.refresh(queued)
    if guard == "allowed":
        assert queued.error_code is None and queued.rows_inserted == 2
        assert any(u.endswith(".js") for u, _, _ in io_mock.calls)
    else:
        assert queued.error_code == (
            "source_unavailable" if guard == "disabled" else "CollectorsLiveDisabled"
        )
        assert io_mock.calls == []


def test_js_zero_subunit_money(
    session: Session, settings: Settings, io_mock: Any, catalog: None
) -> None:
    meta = json.loads(fixture("meta").body or b"")
    meta["currency"] = "JPY"
    io_mock.replies["https://first.test/meta.json"] = Response(json.dumps(meta).encode(), 200)
    body = json.loads(fixture("variant_inventory").body or b"")
    body["variants"][0].update(price=100000, compare_at_price=0)
    io_mock.replies[JS] = Response(json.dumps(body).encode(), 200)
    assert js_run(session, settings).error_code is None
    row = session.scalars(select(VariantSnapshot).where(VariantSnapshot.currency == "JPY")).one()
    assert (row.price_minor, row.compare_at_minor) == (1000, 0)
