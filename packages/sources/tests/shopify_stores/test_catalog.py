import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import URLError

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    RawPayload,
    Source,
    SourceEvent,
    Store,
    VariantSnapshot,
    WorkspaceTrackedStore,
)
from pulso_core.settings import Settings
from pulso_sources import framework, shopify_stores
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    enqueue_run,
    lifecycle,
)
from pulso_sources.shopify_stores.records import Product

from .conftest import FIXTURES, fixture

CATALOG = "https://first.test/products.json?limit=250&page=1"


def run(session: Session, settings: Settings) -> Any:
    queued = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    return shopify_stores.collect(session, queued.id, settings=settings)


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_parse_every_saved_fixture(path: Any, settings: Settings) -> None:
    data = json.loads(path.read_text())
    adapter = shopify_stores.ShopifyAdapter(settings)
    if data.get("parse_error"):
        with pytest.raises(ValueError):
            adapter.parse(fixture(path.stem).body or b"")
    else:
        assert len(adapter.parse(fixture(path.stem).body or b"")) == data["records"]


def test_complete_store_isolated_from_page_two_failure(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    for store_id in (1, 2):
        session.add(
            Listing(
                source_id=1,
                store_id=store_id,
                external_id=f"{store_id}:9999",
                title="Old",
                url=f"https://fixture.test/{store_id}",
            )
        )
    session.commit()
    io_mock.replies[CATALOG] = fixture("page_1")
    io_mock.replies[CATALOG.replace("page=1", "page=2")] = fixture("page_2_failure")
    result = run(session, settings)
    old = list(session.scalars(select(Listing).where(Listing.title == "Old").order_by(Listing.id)))
    assert old[0].delisted_at is None and old[1].delisted_at is not None
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "first.test")).status
        == "partial"
    )
    assert session.get_one(Store, 1).last_crawled_at is None
    assert session.get_one(Store, 2).last_crawled_at is not None
    assert len({call[0] for call in io_mock.calls}) == len(io_mock.calls)


def test_two_pages_then_304_refreshes_without_snapshots(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    io_mock.replies[CATALOG] = fixture("page_1")
    page2 = CATALOG.replace("page=1", "page=2")
    io_mock.replies[page2] = fixture("page_2")
    run(session, settings)
    count = session.scalar(select(func.count()).select_from(ListingSnapshot))
    listing = session.scalar(select(Listing).filter_by(external_id="1:251"))
    assert listing is not None
    before = listing.last_seen_at
    io_mock.calls.clear()
    io_mock.replies[CATALOG] = fixture("not_modified")
    io_mock.replies[page2] = fixture("not_modified")
    result = run(session, settings)
    session.refresh(listing)
    assert listing.last_seen_at > before
    assert session.scalar(select(func.count()).select_from(ListingSnapshot)) == count
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "first.test")).status
        == "success"
    )
    assert not any(url.endswith("robots.txt") for url, _, _ in io_mock.calls)
    assert all(
        headers.get("If-none-match") == '"catalog-v1"'
        for url, _, headers in io_mock.calls
        if url in (CATALOG, page2)
    )
    assert all(row.inventory_quantity is None for row in session.scalars(select(VariantSnapshot)))


@pytest.mark.parametrize("bad", ["bad_parse", "bad_money"])
def test_failed_parse_or_upsert_etag_never_reused(
    session: Session, settings: Settings, io_mock: Any, bad: str
) -> None:
    io_mock.replies[CATALOG] = fixture(bad)
    run(session, settings)
    assert (
        session.scalar(select(func.count()).select_from(Listing).where(Listing.store_id == 1)) == 0
    )
    io_mock.calls.clear()
    io_mock.replies[CATALOG] = fixture("normal")
    run(session, settings)
    headers = next(h for u, _, h in io_mock.calls if u == CATALOG)
    assert "If-none-match" not in headers


def test_blocks_stop_run_and_persist_retry_floor(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    io_mock.replies[CATALOG] = fixture("rate_limited")
    run(session, settings)
    source = session.get_one(Source, 1)
    assert source.retry_not_before is not None
    assert source.retry_not_before.replace(tzinfo=UTC) >= datetime.now(UTC) + timedelta(seconds=59)
    assert not any("second.test" in u for u, _, _ in io_mock.calls)
    io_mock.calls.clear()
    result = run(session, settings.model_copy(update={"collector_retry_wait_cap_seconds": 0}))
    assert result.error_message == "retry_not_before" and io_mock.calls == []


def test_known_403_excluded_on_later_runs(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    io_mock.replies[CATALOG] = Response(b"Forbidden", 403)
    run(session, settings)
    assert session.get_one(Store, 1).status == "blocked"
    io_mock.calls.clear()
    result = run(session, settings)
    assert all("first.test" not in u and "inspireuplift.com" not in u for u, _, _ in io_mock.calls)
    assert session.get_one(
        CollectorRunTarget, (result.id, "shopify_excluded", "first.test:blocked")
    )


@pytest.mark.parametrize("name", ["robots_redirect", "robots_disallow", "password", "headless"])
def test_untrackable_or_robots_failure_never_completes(
    session: Session, settings: Settings, io_mock: Any, name: str
) -> None:
    path = "https://first.test/robots.txt" if name.startswith("robots") else CATALOG
    io_mock.replies[path] = fixture(name)
    result = run(session, settings)
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "first.test")).status
        != "success"
    )
    assert session.get_one(Store, 1).last_crawled_at is None
    if name.startswith("robots"):
        assert CATALOG not in [u for u, _, _ in io_mock.calls]


def test_limiter_user_agent_and_no_retry(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    io_mock.replies[CATALOG] = URLError("offline failure")
    run(session, settings)
    calls = io_mock.calls
    assert [u for u, _, _ in calls].count(CATALOG) == 1
    assert all(b[1] - a[1] >= 2 for a, b in zip(calls, calls[1:], strict=False))
    for domain in ("first.test", "second.test"):
        times = [t for u, t, _ in calls if domain in u]
        assert all(
            b - a >= shopify_stores.STORE_SPACING_SECONDS > 3
            for a, b in zip(times, times[1:], strict=False)
        )
    assert all(h["User-agent"] == settings.collector_user_agent for _, _, h in calls)


def test_fatal_430_disables_once(session: Session, settings: Settings, io_mock: Any) -> None:
    io_mock.replies[CATALOG] = Response(b"Security rejection", 430)
    run(session, settings)
    assert not session.get_one(Source, 1).enabled
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1


@pytest.mark.parametrize("worktree", [False, True])
def test_live_guard_blocks_network(
    session: Session,
    settings: Settings,
    io_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    worktree: bool,
) -> None:
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: worktree)
    with pytest.raises(CollectorsLiveDisabled):
        run(session, settings.model_copy(update={"collectors_live": worktree}))
    assert io_mock.calls == []


def test_approval_and_workspace_tracking_required(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    session.query(WorkspaceTrackedStore).filter_by(store_id=1).delete()
    source = session.get_one(Source, 1)
    source.config = {
        "seed": {**source.config["seed"], "entries": [source.config["seed"]["entries"][0]]}
    }
    session.commit()
    run(session, settings)
    assert io_mock.calls == []
    source.config = {"seed": {**source.config["seed"], "status": "draft"}}
    session.commit()
    run(session, settings)
    assert io_mock.calls == []


def test_offline_fixture_fetch_never_calls_http(settings: Settings, io_mock: Any) -> None:
    adapter = shopify_stores.ShopifyAdapter(settings)
    response = framework.fetch(
        adapter,
        Request(mode="fixture", body=fixture("normal").body),
        settings=settings.model_copy(update={"collectors_live": False}),
    )
    assert isinstance(adapter.parse(response.body or b"")[0], Product)
    assert io_mock.calls == []


def test_five_429_runs_disable_and_same_slot_delivery_is_noop(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Clock:
        at = datetime.now(UTC)

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls.at

    monkeypatch.setattr(lifecycle, "datetime", Clock)
    io_mock.replies["https://first.test/robots.txt"] = fixture("rate_limited")
    for _ in range(5):
        result = run(session, settings)
        count = len(io_mock.calls)
        shopify_stores.collect(session, result.id, settings=settings)
        assert len(io_mock.calls) == count
        Clock.at += timedelta(seconds=61)
        io_mock.now += 61
    assert len(io_mock.calls) == 5
    assert not session.get_one(Source, 1).enabled
    assert session.get_one(Source, 1).consecutive_block_count == 5
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1


def test_blocks_disable_once_while_robots_answers_200(
    session: Session, settings: Settings, io_mock: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    # XR-11: robots.txt 200 before each store's JSON must not reset the block count.
    class Clock:
        at = datetime.now(UTC)

        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return cls.at

    monkeypatch.setattr(lifecycle, "datetime", Clock)
    io_mock.replies["https://first.test/meta.json"] = fixture("rate_limited")
    for _ in range(settings.collector_block_threshold):
        assert run(session, settings).error_message == "http_429"
        Clock.at += timedelta(seconds=61)
        io_mock.now += 61
    source = session.get_one(Source, 1)
    assert not source.enabled and source.consecutive_block_count == 5
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1
    assert [u.rsplit("/", 1)[1] for u, _, _ in io_mock.calls] == ["robots.txt", "meta.json"] * 5
    run(session, settings)
    assert len(io_mock.calls) == 10


@pytest.mark.parametrize("path", ["/robots.txt", "/meta.json", "/products.json?limit=250&page=1"])
def test_unsolicited_304_never_confers_coverage(
    session: Session, settings: Settings, io_mock: Any, path: str
) -> None:
    io_mock.replies["https://first.test" + path] = fixture("not_modified")
    result = run(session, settings)
    assert session.get_one(Store, 1).last_crawled_at is None
    assert (
        session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "first.test")).status
        == "partial"
    )


def test_currency_change_does_not_reuse_etag_or_suppress_snapshot(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    run(session, settings)
    io_mock.calls.clear()
    meta = json.loads(fixture("meta").body or b"")
    meta["currency"] = "EUR"
    io_mock.replies["https://first.test/meta.json"] = Response(json.dumps(meta).encode(), 200)
    run(session, settings)
    headers = next(h for u, _, h in io_mock.calls if u == CATALOG)
    assert "If-none-match" not in headers
    rows = list(
        session.scalars(
            select(ListingSnapshot)
            .join(Listing)
            .where(Listing.store_id == 1)
            .order_by(ListingSnapshot.id)
        )
    )
    assert [r.currency for r in rows] == ["USD", "EUR"]
    assert all(
        r.price_min_minor == r.price_max_minor == 2499 and r.compare_at_min_minor == 2999
        for r in rows
    )


def test_configured_global_budget_and_robots_delay(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    io_mock.replies["https://first.test/robots.txt"] = Response(
        b"User-agent: *\nCrawl-delay: 90\nDisallow: /cart\n", 200, "text/plain"
    )
    run(session, settings.model_copy(update={"shopify_requests_per_minute": 1}))
    times = [t for _, t, _ in io_mock.calls]
    assert all(b - a >= 60 for a, b in zip(times, times[1:], strict=False))
    first = [t for u, t, _ in io_mock.calls if "first.test" in u]
    assert all(b - a >= 90 for a, b in zip(first, first[1:], strict=False))


def test_replay_is_idempotent_without_regressing_current_freshness(
    session: Session, settings: Settings, io_mock: Any
) -> None:
    run(session, settings)
    listing = session.scalar(select(Listing).filter_by(external_id="1:1"))
    assert listing is not None
    before = listing.last_seen_at
    payload = session.scalar(
        select(RawPayload).where(RawPayload.request["url"].as_string() == CATALOG)
    )
    assert payload is not None
    payload.captured_at = payload.captured_at.replace(tzinfo=UTC)
    adapter = shopify_stores.ShopifyAdapter(settings)
    stats = adapter.upsert(
        session,
        adapter.parse(fixture("normal").body or b""),
        payload,
        parser_version=adapter.parser_version,
    )
    assert stats.inserted == 0
    assert listing.last_seen_at == before
