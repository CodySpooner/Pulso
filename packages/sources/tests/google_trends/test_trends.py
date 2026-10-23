import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr
from sqlalchemy import Integer, MetaData, func, select
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import RawPayload, SearchTrend, Source
from pulso_core.settings import Settings
from pulso_sources import google_trends as trends
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    enqueue_run,
    execute_run,
    fetch,
)
from pulso_sources.imports import ImportData, parse_csv

if TYPE_CHECKING:
    from framework.test_block_retry import Network

pytest_plugins = (
    "packages.sources.tests.framework.conftest",
    "packages.sources.tests.framework.test_block_retry",
)
FIXTURES = Path(__file__).parent / "fixtures"


def body(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


@pytest.fixture(autouse=True)
def setup(session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    table = metadata.tables["search_trends"]
    table.c.id.type = Integer()
    table.create(session.get_bind())
    source = session.get_one(Source, 1)
    source.key, source.config = "google_trends", json.loads(body("seed"))
    session.commit()
    settings.serpapi_api_key = SecretStr("fixture")
    monkeypatch.setattr(trends, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(trends, "get_settings", lambda: settings)


@pytest.mark.parametrize(
    "name,count,partial", [("normal", 2, False), ("partial", 2, True), ("no_data", 0, False)]
)
def test_parse(name: str, count: int, partial: bool) -> None:
    rows = trends.GoogleTrendsParser().parse(body(name))
    assert len(rows) == count
    if rows:
        assert rows[-1].is_partial is partial and rows[0].value == 50
        assert rows[0].observed_for.isoformat() == "2026-10-19"


def test_captures_replay_and_csv(session: Session) -> None:
    adapter = trends.GoogleTrendsParser()
    rows = adapter.parse(body("normal"))
    for raw_id in (1, 2):
        payload = RawPayload(id=raw_id, source_id=1, captured_at=datetime(2026, 10, 22, tzinfo=UTC))
        assert adapter.upsert(session, rows, payload, parser_version="1").inserted == 2
        assert adapter.upsert(session, rows, payload, parser_version="1").unchanged == 2
    csv_body = b"keyword,date,interest\nexample keyword,2026-10-19,50\n"
    adapter = trends.GoogleTrendsParser(
        ImportData(
            "csv", parse_csv("google_trends", csv_body, as_of=payload.captured_at.date()), None
        ),
    )
    payload.id = 3
    assert (
        adapter.upsert(session, adapter.parse(csv_body), payload, parser_version="1").inserted == 1
    )
    saved = list(session.scalars(select(SearchTrend).order_by(SearchTrend.id)))
    assert len(saved) == 5 and [r.raw_payload_id for r in saved] == [1, 1, 2, 2, 3]
    assert saved[0].value == saved[-1].value == 50 and saved[-1].window == "manual"


@pytest.mark.parametrize(
    "name,status,code",
    [
        ("error", 200, "serpapi_error"),
        ("invalid_key", 401, "serpapi_invalid_key"),
        ("exhausted", 200, "serpapi_searches_exhausted"),
        ("rate_limited", 429, "serpapi_rate_limited"),
        ("error", 403, "serpapi_forbidden"),
    ],
)
def test_errors(name: str, status: int, code: str) -> None:
    assert trends.error_code(body(name), status) == code
    with pytest.raises(trends.TrendsError, match=trends.error_code(body(name))):
        trends.GoogleTrendsParser().parse(body(name))


def test_monthly_reservation_before_http(
    session: Session, settings: Settings, network: Network
) -> None:
    source = session.get_one(Source, 1)
    at = datetime.now(UTC)
    for _ in range(5 * 50):
        trends.reserve(source, 250, at)
        session.commit()
    session.expire_all()
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        network[0],
        trends.plan(session),
        settings=settings,
        request_hook=trends.request_hook,
    )
    assert run.error_message == "trends_monthly_budget_exhausted"
    assert run.status == "partial" and run.http_requests == network[1].call_count == 0
    with pytest.raises(trends.TrendsError):
        trends.reserve(
            source, 250, at.replace(day=1, hour=0).astimezone(timezone(-timedelta(hours=5)))
        )
    trends.reserve(source, 250, at + timedelta(days=32))
    assert source.config["trends_quota"]["used"] == 1
    with pytest.raises(ValueError):
        trends.reserve(source, 251, at)


def test_plan_guard_and_missing_key(session: Session, settings: Settings, network: Network) -> None:
    requests = list(trends.plan(session)[0].requests)
    assert requests[0].params == {**trends.PARAMS, "q": "example keyword"}
    settings.collectors_live = False
    with pytest.raises(CollectorsLiveDisabled):
        fetch(network[0], requests[0], settings=settings)
    settings.collectors_live, settings.serpapi_api_key = True, None
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        network[0],
        trends.plan(session),
        settings=settings,
        request_hook=trends.request_hook,
    )
    assert run.error_message == "serpapi_missing_key"
    assert network[1].call_count == 0
    source = session.get_one(Source, 1)
    source.config = json.loads(body("seed").replace(b"example keyword", b"one,two"))
    with pytest.raises(ValueError, match="one keyword"):
        trends.plan(session)
    source.config = {}
    assert trends.plan(session) == []
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 0


def test_reservation_commits_even_on_transport_failure(
    session: Session, settings: Settings, network: Network
) -> None:
    settings.collector_max_retries = 0
    network[1].side_effect = ConnectionError("fixture failure")
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        network[0],
        trends.plan(session),
        settings=settings,
        request_hook=trends.request_hook,
    )
    session.expire_all()
    assert session.get_one(Source, 1).config["trends_quota"]["used"] == 2
    assert network[1].call_count == 2
    assert not any(active for _, active in network[2])


@pytest.mark.parametrize("value", [-1, 101, 1.5, True, "50"])
def test_invalid_values(value: object) -> None:
    data = json.loads(body("normal"))
    data["interest_over_time"]["timeline_data"][0]["values"][0]["extracted_value"] = value
    with pytest.raises(ValueError):
        trends.GoogleTrendsParser().parse(json.dumps(data).encode())


def test_invalid_partial_flag() -> None:
    data = body("partial").replace(b'"is_partial":true', b'"is_partial":"false"')
    with pytest.raises(ValueError):
        trends.GoogleTrendsParser().parse(data)
