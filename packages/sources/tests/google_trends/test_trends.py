import json
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest
from pydantic import SecretStr
from sqlalchemy import Integer, MetaData, func, select
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import CollectorRun, RawPayload, SearchTrend, Source, SourceEvent
from pulso_core.settings import Settings
from pulso_sources import google_trends as trends
from pulso_sources import storage
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    enqueue_run,
    execute_run,
    fetch,
    lifecycle,
)
from pulso_sources.google_trends import live
from pulso_sources.imports import ImportData, commit_import, parse_csv
from pulso_workers import registration, tasks

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
    session.expire_on_commit = False  # SQLite reloads lose timestamptz's UTC information.
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
    monkeypatch.setattr(live, "get_settings", lambda: settings)
    monkeypatch.setattr(registration, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_session", lambda: nullcontext(session))
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))


@pytest.mark.parametrize(
    "name,count,partial",
    [("normal", 2, False), ("string_echo", 2, False), ("partial", 2, True), ("no_data", 0, False)],
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
    parse_code = trends.error_code(body(name))
    with pytest.raises(
        trends.TrendsError if parse_code in trends.ACCOUNT_ERRORS else ValueError, match=parse_code
    ):
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
    assert "trends_quota" not in source.config
    assert collect(session, settings).error_code == "serpapi_missing_key"
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


@pytest.fixture
def http(network: Network, monkeypatch: pytest.MonkeyPatch) -> Mock:
    connection = Mock()
    response = connection.getresponse.return_value
    response.status, response.read.return_value = 200, body("normal")
    response.getheader.return_value = "application/json"
    response.getheaders.return_value = []
    response.read.side_effect = lambda: response.read.return_value.replace(
        b"example keyword",
        parse_qs(urlsplit(connection.request.call_args.args[1]).query)["q"][0].encode(),
    )
    monkeypatch.setattr(live, "HTTPSConnection", Mock(return_value=connection))
    return connection


def collect(session: Session, settings: Settings) -> CollectorRun:
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    tasks.collect_run(run.id)
    session.refresh(run)
    return run


@pytest.mark.parametrize("fixture,rows", [("normal", 4), ("no_data", 0)])
def test_live_capture_contract(
    session: Session,
    settings: Settings,
    http: Mock,
    fixture: str,
    rows: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http.getresponse.return_value.read.return_value = body(fixture)
    monkeypatch.setenv("HTTPS_PROXY", "http://unused.example.test")
    settings.serpapi_api_key = SecretStr("fixture-secret")

    def sent(*args: object, **kwargs: object) -> None:
        assert not session.in_transaction()
        with Session(session.get_bind()) as observer:
            assert (
                observer.get_one(Source, 1).config["trends_quota"]["used"]
                == http.request.call_count
            )

    http.request.side_effect = sent
    run = collect(session, settings)
    assert run.status == "success" and run.rows_inserted == rows
    assert run.http_requests == 2
    live.HTTPSConnection.assert_called_with(  # type: ignore[attr-defined]
        "serpapi.com", timeout=settings.collector_request_timeout_seconds
    )
    args, kwargs = http.request.call_args
    assert args[0] == "GET" and urlsplit(args[1]).path == "/search.json"
    params = parse_qs(urlsplit(args[1]).query)
    assert params == {
        **{k: [str(v)] for k, v in trends.PARAMS.items()},
        "q": ["another keyword"],
        "api_key": ["fixture-secret"],
    }
    assert kwargs["headers"]["User-Agent"] == settings.collector_user_agent
    captures = list(session.scalars(select(RawPayload)))
    assert len(captures) == 2 and storage.read_capture(captures[0]) == body(fixture)
    assert "fixture-secret" not in repr([r.request for r in captures])
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == rows
    http.close.assert_called()


@pytest.mark.parametrize(
    "status,fixture,code",
    [
        (401, "invalid_key", "serpapi_invalid_key"),
        (200, "invalid_key", "serpapi_invalid_key"),
        (200, "exhausted", "serpapi_searches_exhausted"),
        (429, "exhausted", "serpapi_searches_exhausted"),
        (200, "error", "serpapi_error"),
        (403, "error", "serpapi_forbidden"),
        (429, "rate_limited", "serpapi_rate_limited"),
    ],
)
def test_response_failure(
    session: Session,
    settings: Settings,
    http: Mock,
    status: int,
    fixture: str,
    code: str,
) -> None:
    response = http.getresponse.return_value
    response.status, response.read.return_value = status, body(fixture)
    response.getheaders.return_value = [
        ("Retry-After", "3888000" if fixture == "exhausted" and status == 429 else "3600")
    ]
    settings.collector_block_threshold = 1
    run = collect(session, settings)
    assert run.status == "partial" and run.error_code == run.error_message == code
    attempts = 2 if code == "serpapi_error" else 1
    assert run.http_requests == attempts
    assert session.scalar(select(func.count()).select_from(RawPayload)) == attempts
    session.expire_all()
    source = session.get_one(Source, 1)
    assert source.config["trends_quota"]["used"] == attempts
    blocked = status in {403, 429}
    assert source.consecutive_block_count == int(blocked)
    assert source.enabled == (not blocked and code != "serpapi_invalid_key")
    if blocked:
        assert source.retry_not_before is not None
        assert source.retry_not_before >= datetime.now(UTC) + timedelta(minutes=59)
    if fixture == "exhausted":
        deadline = (datetime.now(UTC).replace(day=28) + timedelta(days=4)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        assert source.retry_not_before is not None and source.retry_not_before >= deadline
        if status == 429:
            assert source.retry_not_before >= datetime.now(UTC) + timedelta(days=44)
    if not source.enabled or fixture == "exhausted":
        collect(session, settings)
        assert http.request.call_count == 1
        assert session.scalar(select(func.count()).select_from(SourceEvent)) == int(
            not source.enabled
        )


def test_transport_redaction_redirect_and_retries(
    session: Session,
    settings: Settings,
    http: Mock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings.collector_max_retries = 1
    http.request.side_effect = OSError("fixture secret in URL")
    run = collect(session, settings)
    assert run.http_requests == 4
    assert session.get_one(Source, 1).config["trends_quota"]["used"] == 4
    assert "fixture secret" not in str(run.error_message) + caplog.text
    with pytest.raises(ConnectionError) as caught:
        live.GoogleTrendsAdapter().fetch(
            list(trends.plan(session)[0].requests)[0], user_agent="fixture"
        )
    assert str(caught.value) == "SerpApi transport failed" and caught.value.__suppress_context__
    http.request.side_effect = None
    http.getresponse.return_value.status = 302
    http.getresponse.return_value.getheaders.return_value = [
        ("Location", "https://other.example.test")
    ]
    run = collect(session, settings)
    assert run.error_message == "http_302" and run.http_requests == 2


def test_registered_csv_stays_disabled(session: Session, settings: Settings, http: Mock) -> None:
    from pulso_workers.tasks import PLANS

    source = session.get_one(Source, 1)
    source.enabled = False
    session.commit()
    registered = PLANS["google_trends"](session, source, "trends")
    assert isinstance(registered.adapter, live.GoogleTrendsAdapter)
    assert registered.wall_time_seconds == settings.trends_wall_time_seconds
    with pytest.raises(ValueError):
        PLANS["google_trends"](session, source, "catalog")
    csv = b"keyword,date,interest\nexample keyword,2026-10-19,50\n"
    run = commit_import(session, "google_trends", csv, settings=settings)
    assert run.status == "success" and run.rows_inserted == 1 and not source.enabled
    assert commit_import(session, "google_trends", csv, settings=settings).status == "skipped"
    http.request.assert_not_called()


def test_keyword_error_does_not_stop_later_keywords(
    session: Session,
    settings: Settings,
    http: Mock,
) -> None:
    http.getresponse.return_value.read.side_effect = [body("error"), body("string_echo")]
    run = collect(session, settings)
    assert (run.status, run.error_code, run.http_requests, run.rows_inserted) == (
        "partial",
        "serpapi_error",
        2,
        2,
    )


def test_exhaustion_resumes_at_next_utc_month(
    session: Session,
    settings: Settings,
    http: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings.collector_retry_wait_cap_seconds = 1
    clock = Mock(wraps=datetime)
    clock.now.return_value = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    for module in (trends, live, lifecycle):
        monkeypatch.setattr(module, "datetime", clock)
    http.getresponse.return_value.read.return_value = body("exhausted")
    assert collect(session, settings).error_code == "serpapi_searches_exhausted"
    assert collect(session, settings).http_requests == 0
    clock.now.return_value = datetime(2027, 1, 1, tzinfo=UTC)
    http.getresponse.return_value.read.return_value = body("no_data")
    assert collect(session, settings).status == "success"
    assert session.get_one(Source, 1).config["trends_quota"] == {"month": "2027-01", "used": 2}


def test_three_capture_cutoff(
    session: Session,
    settings: Settings,
    http: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = []
    clock = Mock(wraps=datetime)
    monkeypatch.setattr(lifecycle, "datetime", clock)
    for day in (21, 22, 23):
        clock.now.return_value = datetime(2026, 10, day, tzinfo=UTC)
        run = collect(session, settings)
        captures = list(session.scalars(select(RawPayload).where(RawPayload.run_id == run.id)))
        ids.append(captures[0].id)
    assert trends.series_as_of(session, "example keyword", date(2026, 10, 20)) == []
    for day, raw_id in zip((21, 22, 23), ids, strict=True):
        rows = trends.series_as_of(session, "example keyword", date(2026, 10, day))
        assert len(rows) == 2 and {r.raw_payload_id for r in rows} == {raw_id}
    http.getresponse.return_value.read.return_value = body("no_data")
    clock.now.return_value = datetime(2026, 10, 23, 1, tzinfo=UTC)
    collect(session, settings)
    assert trends.series_as_of(session, "example keyword", date(2026, 10, 23)) == []
