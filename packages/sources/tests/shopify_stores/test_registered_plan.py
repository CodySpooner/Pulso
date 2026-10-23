from collections.abc import Callable
from contextlib import nullcontext
from typing import Any
from unittest.mock import Mock
from urllib.error import URLError

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    Source,
    SourceEvent,
    Store,
    VariantSnapshot,
)
from pulso_core.settings import Settings
from pulso_sources import framework, shopify_stores
from pulso_sources.framework import Response, enqueue_run
from pulso_workers import celery_app, registration, tasks
from pulso_workers.celery_app import app

from .conftest import fixture
from .test_catalog import CATALOG


@pytest.fixture
def registered(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> Callable[[], CollectorRun]:
    monkeypatch.setattr(celery_app, "get_settings", lambda: settings)
    app.loader.import_default_modules()
    monkeypatch.setattr(registration, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_session", lambda: nullcontext(session))
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))

    def run() -> CollectorRun:
        queued = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        tasks.collect_run(queued.id)
        session.expire_all()
        return session.get_one(CollectorRun, queued.id)

    return run


@pytest.mark.parametrize("entry", ["collect", "registered"])
def test_both_entry_paths_match_requests_observations_and_finalization(
    session: Session,
    settings: Settings,
    io_mock: Any,
    registered: Callable[[], CollectorRun],
    entry: str,
) -> None:
    for store_id in (1, 2):
        session.add(
            Listing(
                source_id=1,
                store_id=store_id,
                external_id=f"{store_id}:999",
                title="Old",
                url=f"https://fixture.test/{store_id}",
            )
        )
    session.commit()
    io_mock.replies[CATALOG.replace("first.test", "second.test")] = Response(b"Unavailable", 503)
    if entry == "collect":
        queued = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        result = shopify_stores.collect(session, queued.id, settings=settings)
    else:
        result = registered()
    assert result.status == "partial" and result.error_code == "ResponseFailed"
    expected_urls = [
        f"https://{domain}{path}"
        for domain in ("first.test", "second.test")
        for path in ("/robots.txt", "/meta.json", "/products.json?limit=250&page=1")
    ]
    assert [(url, headers) for url, _, headers in io_mock.calls] == [
        (url, {"User-agent": settings.collector_user_agent}) for url in expected_urls
    ]
    observed = session.scalars(select(ListingSnapshot)).one()
    assert (
        session.get_one(Listing, observed.listing_id).external_id,
        observed.currency,
        observed.price_min_minor,
        observed.price_max_minor,
        observed.compare_at_min_minor,
        observed.available,
    ) == ("1:1", "USD", 2499, 2499, 2999, True)
    variant = session.scalars(select(VariantSnapshot)).one()
    assert (variant.price_minor, variant.compare_at_minor, variant.inventory_quantity) == (
        2499,
        2999,
        None,
    )
    session.expire_all()
    for store_id, domain, status in ((1, "first.test", "success"), (2, "second.test", "partial")):
        target = session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", domain))
        assert target.status == status
        expected_at = target.captured_at if status == "success" else None
        assert session.get_one(Store, store_id).last_crawled_at == expected_at
        old = session.scalars(select(Listing).filter_by(external_id=f"{store_id}:999")).one()
        assert old.delisted_at == expected_at
    current = session.scalars(select(Listing).filter_by(external_id="1:1")).one()
    assert current.last_seen_at == session.get_one(Store, 1).last_crawled_at
    assert current.delisted_at is None
    count = len(io_mock.calls)
    tasks.collect_run(result.id)
    shopify_stores.collect(session, result.id, settings=settings)
    assert len(io_mock.calls) == count


@pytest.mark.parametrize("response", [Response(b"Unavailable", 503), URLError("fixture offline")])
def test_registered_transient_failure_never_retries_or_defers_other_stores(
    session: Session, io_mock: Any, registered: Callable[[], CollectorRun], response: Any
) -> None:
    io_mock.replies[CATALOG] = response
    result = registered()
    assert result.error_code in {"ResponseFailed", "ConnectionError"}
    assert result.error_message != "same_url_in_run"
    urls = [url for url, _, _ in io_mock.calls]
    assert urls.count(CATALOG) == 1 and len(urls) == len(set(urls))
    assert session.get_one(Store, 1).last_crawled_at is None
    assert session.get_one(Store, 2).last_crawled_at is not None
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "second.test")).status
        == "success"
    )


def test_registered_preloads_successful_etags_and_robots(
    session: Session, io_mock: Any, registered: Callable[[], CollectorRun]
) -> None:
    registered()
    before = session.get_one(Store, 1).last_crawled_at
    assert before is not None
    counts = [
        session.scalar(select(func.count()).select_from(m))
        for m in (ListingSnapshot, VariantSnapshot)
    ]
    io_mock.calls.clear()
    for domain in ("first.test", "second.test"):
        io_mock.replies[CATALOG.replace("first.test", domain)] = fixture("not_modified")
    registered()
    assert len(io_mock.calls) == 4
    assert not any(url.endswith("robots.txt") for url, _, _ in io_mock.calls)
    assert all(
        headers.get("If-none-match") == '"catalog-v1"'
        for url, _, headers in io_mock.calls
        if "products.json" in url
    )
    assert [
        session.scalar(select(func.count()).select_from(m))
        for m in (ListingSnapshot, VariantSnapshot)
    ] == counts
    after = session.get_one(Store, 1).last_crawled_at
    assert after is not None and after > before


@pytest.mark.parametrize("guard", ["disabled", "worktree", "live_off"])
def test_registration_enables_nothing_and_live_guards_hold(
    session: Session,
    settings: Settings,
    io_mock: Any,
    registered: Callable[[], CollectorRun],
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
) -> None:
    source = session.get_one(Source, 1)
    source.enabled = False
    session.commit()
    app.loader.import_default_modules()
    plan = tasks.PLANS[source.key](session, source, "catalog")
    assert not source.enabled and io_mock.calls == []
    assert plan.collector_max_retries == 0 and plan.finalize is not None
    with pytest.raises(ValueError, match="Unsupported Shopify job"):
        tasks.PLANS[source.key](session, source, "unsupported")
    if guard != "disabled":
        source.enabled = True
        session.commit()
        monkeypatch.setattr(framework, "is_linked_worktree", lambda _: guard == "worktree")
        monkeypatch.setattr(
            tasks,
            "get_settings",
            lambda: settings.model_copy(update={"collectors_live": guard == "worktree"}),
        )
    result = registered()
    assert result.error_code == ("ValueError" if guard == "disabled" else "CollectorsLiveDisabled")
    assert io_mock.calls == []


def test_registered_uses_shopify_block_hook(
    session: Session, io_mock: Any, registered: Callable[[], CollectorRun]
) -> None:
    io_mock.replies[CATALOG] = Response(b"Blocked", 430)
    registered()
    assert not session.get_one(Source, 1).enabled
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1
    assert all("second.test" not in url for url, _, _ in io_mock.calls)
