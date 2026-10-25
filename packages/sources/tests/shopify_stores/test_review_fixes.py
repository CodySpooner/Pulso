from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRunTarget, RawPayload
from pulso_core.settings import Settings
from pulso_sources import shopify_stores
from pulso_sources.framework import Response

from .test_catalog import CATALOG, run


@pytest.mark.parametrize(
    ("body", "delay"),
    [
        ("User-agent: *\nCrawl-delay: 10.5\n", 10.5),
        ("User-agent: *\nCrawl-delay: 10 # slow\nCrawl-delay: 7.25\n", 10),
        ("User-agent: Googlebot\nCrawl-delay: 30\n\nUser-agent: *\nCrawl-delay: 1\n", 30),
        ("User-agent: *\nCrawl-delay: inf\nCrawl-delay: nan\nCrawl-delay: 1e999\n", 0),
        ("User-agent: *\nCrawl-delay: -4\nCrawl-delay: soon\nCrawl-delay:\n", 0),
        ("User-agent: *\nRequest-rate: 2/10\nCrawl-delay: 3\n", 5),
        ("User-agent: *\nDisallow: /cart\n", 0),
    ],
)
def test_robots_delay_is_the_largest_finite_value(body: str, delay: float) -> None:
    # XR-14: every Crawl-delay in the file, fractions included, can only slow the crawl.
    assert shopify_stores.read_robots(body)[1] == delay


def test_zero_request_rate_is_a_named_refusal() -> None:
    with pytest.raises(shopify_stores.RobotsZeroRate):
        shopify_stores.read_robots("User-agent: *\nRequest-rate: 0/1\n")


@pytest.mark.parametrize(
    ("domain", "age", "rpm", "existing_wait", "expected_wait"),
    [
        ("first.test", 0, 30, 0, 10),
        ("second.test", 0, 30, 0, 2),
        ("second.test", 0, 1, 0, 60),
        ("first.test", 3, 30, 0, 7),
        ("first.test", 60, 30, 0, 0),
        ("first.test", 0, 30, 20, 20),
    ],
)
def test_run_seeds_spacing_from_captures_after_clock_reset(
    session: Session,
    settings: Settings,
    io_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    domain: str,
    age: int,
    rpm: int,
    existing_wait: int,
    expected_wait: int,
) -> None:
    run(session, settings)
    now = datetime.now(UTC)
    captures = list(session.scalars(select(RawPayload).order_by(RawPayload.id)))
    for payload in captures:
        payload.captured_at = now - timedelta(days=1)
    recent = next(payload for payload in captures if payload.request["domain"] == domain)
    recent.captured_at = now - timedelta(seconds=age)
    recent.status_code = 503  # Pacing includes failed captures, unlike the ETag cache.
    session.commit()

    class Clock:
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return now

    monkeypatch.setattr(shopify_stores, "datetime", Clock)
    monkeypatch.setattr(shopify_stores, "_next_global", 0)
    monkeypatch.setattr(
        shopify_stores,
        "_next_store",
        {"first.test": io_mock.now + existing_wait} if existing_wait else {},
    )
    io_mock.calls.clear()
    started = io_mock.now
    run(session, settings.model_copy(update={"shopify_requests_per_minute": rpm}))
    assert io_mock.calls[0][0].startswith("https://first.test/")
    assert io_mock.calls[0][1] - started == pytest.approx(expected_wait)


@pytest.mark.parametrize("hours", [23, 24, 25])
def test_robots_cache_expires_at_24_hours(
    session: Session,
    settings: Settings,
    io_mock: Any,
    hours: int,
) -> None:
    run(session, settings)
    for payload in session.scalars(select(RawPayload)):
        payload.captured_at -= timedelta(hours=hours)
    session.commit()
    robots = "https://first.test/robots.txt"
    io_mock.replies[robots] = Response(b"User-agent: *\nDisallow: /products.json\n", 200)
    io_mock.calls.clear()
    result = run(session, settings)
    urls = [url for url, _, _ in io_mock.calls]
    expired = hours >= 24
    assert (robots in urls) == expired
    assert (CATALOG not in urls) == expired
    target = session.get_one(CollectorRunTarget, (result.id, "shopify_catalog", "first.test"))
    assert (target.status != "success") == expired
