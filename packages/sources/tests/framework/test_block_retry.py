import io
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, event, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session, attributes
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import CollectorRun, RawPayload, Source, SourceEvent
from pulso_core.settings import Settings
from pulso_sources import framework, storage
from pulso_sources.framework import Request, Response, Target, enqueue_run, execute_run, lifecycle

from .test_lifecycle import FakeAdapter

type Network = tuple[FakeAdapter, Mock, list[tuple[str, bool]]]


@pytest.fixture
def session() -> Iterator[Session]:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in [
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
    ]:
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSON):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)

    # SQLite drops timezone info; PostgreSQL's timestamptz returns aware UTC values.
    def utc(source: Source, *_: Any) -> None:
        if source.retry_not_before is not None:
            attributes.set_committed_value(
                source, "retry_not_before", source.retry_not_before.replace(tzinfo=UTC)
            )

    event.listen(Source, "load", utc)
    event.listen(Source, "refresh", utc)
    try:
        with Session(engine) as session:
            session.add(
                Source(id=1, key="fixture", name="Fixture", type="api", phase=1, enabled=True)
            )
            session.commit()
            yield session
    finally:
        event.remove(Source, "load", utc)
        event.remove(Source, "refresh", utc)
        engine.dispose()


@pytest.fixture
def network(session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Network:
    active = False
    calls: list[tuple[str, bool]] = []

    def begin(_: Connection) -> None:
        nonlocal active
        active = True

    def end(_: Connection) -> None:
        nonlocal active
        active = False

    engine = session.get_bind()
    event.listen(engine, "begin", begin)
    event.listen(engine, "commit", end)
    event.listen(engine, "rollback", end)
    client = MagicMock()
    objects: dict[str, bytes] = {}

    def put(**kwargs: Any) -> None:
        calls.append(("put", active))
        objects[kwargs["Key"]] = kwargs["Body"]

    def get(**kwargs: Any) -> dict[str, io.BytesIO]:
        calls.append(("get", active))
        return {"Body": io.BytesIO(objects[kwargs["Key"]])}

    responses = Mock(return_value=Response(b"ok", 200))

    def fetch(*args: Any, **kwargs: Any) -> Response:
        calls.append(("fetch", active))
        return responses(*args, **kwargs)  # type: ignore[no-any-return]

    client.put_object.side_effect, client.get_object.side_effect = put, get
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(FakeAdapter, "fetch", fetch)
    settings.collectors_live = True
    settings.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    return FakeAdapter(), responses, calls


@pytest.mark.parametrize("body", [b"ok", b"broken"])
def test_network_has_no_open_transaction(
    session: Session, settings: Settings, network: Network, body: bytes
) -> None:
    adapter, responses, calls = network
    responses.side_effect = [Response(body, 200), Response(b"ok", 200)]
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    targets = [Target("catalog", str(n), [Request()]) for n in range(2)]
    execute_run(session, run.id, adapter, targets, settings=settings)
    assert run.status == ("partial" if body == b"broken" else "success")
    assert calls == [("fetch", False), ("put", False), ("get", False)] * 2


@pytest.mark.parametrize("status,threshold", [(429, 5), (403, 5), (430, 5), (429, 2)])
def test_blocks_stop_plan_and_disable_once_across_runs(
    session: Session,
    settings: Settings,
    network: Network,
    status: int,
    threshold: int,
) -> None:
    adapter, responses, calls = network
    settings.collector_block_threshold = threshold
    responses.return_value = Response(b"blocked", status)
    for i in range(threshold + 1):
        session.expire_all()
        run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        targets = [Target("catalog", str(n), [Request(), Request()]) for n in range(2)]
        execute_run(session, run.id, adapter, targets, settings=settings)
        assert run.status == "partial" and not run.complete
        assert run.http_requests == (i < threshold)
    source = session.get_one(Source, 1)
    events = list(session.scalars(select(SourceEvent)))
    assert source.consecutive_block_count == threshold and not source.enabled
    assert source.status == "blocked" and source.last_status_code == status
    assert source.disabled_at is not None
    assert len(events) == 1 and events[0].action == "disable"
    assert events[0].reason == source.disabled_reason == f"consecutive_blocks:http_{status}"
    assert responses.call_count == threshold
    assert not any(active for _, active in calls)


class Clock:
    now = datetime(2026, 10, 22, tzinfo=UTC)
    in_transaction = False

    def __init__(self) -> None:
        self.waits: list[float] = []


@pytest.fixture
def clock(session: Session, monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    engine = session.get_bind()
    event.listen(engine, "begin", lambda _: setattr(clock, "in_transaction", True))
    event.listen(engine, "commit", lambda _: setattr(clock, "in_transaction", False))
    event.listen(engine, "rollback", lambda _: setattr(clock, "in_transaction", False))

    def sleep(seconds: float) -> None:
        assert not clock.in_transaction
        clock.waits.append(seconds)
        clock.now += timedelta(seconds=seconds)

    monkeypatch.setattr(lifecycle, "datetime", Mock(now=lambda _: clock.now))
    monkeypatch.setattr(time, "monotonic", lambda: clock.now.timestamp())
    monkeypatch.setattr(time, "sleep", sleep)
    return clock


@pytest.mark.parametrize("status", [403, 429, 430, 503])
@pytest.mark.parametrize("http_date", [False, True])
def test_retry_deadline_is_atomic_and_respected_across_runs(
    session: Session,
    settings: Settings,
    network: Network,
    clock: Clock,
    status: int,
    http_date: bool,
) -> None:
    adapter, responses, calls = network
    deadline = clock.now + timedelta(seconds=1200)
    header = format_datetime(deadline, usegmt=True) if http_date else "1200"
    responses.side_effect = [
        Response(b"wait", status, headers={"rEtRy-AfTeR": header}),
        Response(b"ok", 200),
    ]
    committed: list[datetime | None] = []

    def inspect_commit(_: Session) -> None:
        with Session(session.get_bind()) as reader:
            if reader.scalar(select(RawPayload.id).limit(1)) is not None:
                committed.append(reader.get_one(Source, 1).retry_not_before)

    for advance in [0, 0, 600]:
        clock.now += timedelta(seconds=advance)
        # A new Session makes the later-run guarantee independent of the identity map.
        with Session(session.get_bind()) as later:
            event.listen(later, "after_commit", inspect_commit)
            run = enqueue_run(later, source_id=1, trigger="manual", publish=lambda _: None)
            result = execute_run(
                later, run.id, adapter, [Target("catalog", "a", [Request()])], settings=settings
            )
            assert result.status == ("success" if advance else "partial")
        if not advance:
            assert responses.call_count == 1 and not clock.waits
    # The response and deadline are visible together at the first capture commit.
    assert committed and all(value == deadline for value in committed)
    assert clock.waits == [600] and clock.now == deadline
    assert responses.call_count == 2 and not any(active for _, active in calls)


def test_503_waits_before_retry_and_hook_commits_before_each_attempt(
    session: Session,
    settings: Settings,
    network: Network,
    clock: Clock,
) -> None:
    adapter, responses, calls = network
    order: list[str] = []
    replies = iter([Response(b"busy", 503, headers={"Retry-After": "120"}), Response(b"ok", 200)])

    def response(*_: Any, **__: Any) -> Response:
        with Session(session.get_bind()) as reader:
            assert reader.get_one(Source, 1).config["quota"] == responses.call_count
        order.append("fetch")
        return next(replies)

    def hook(
        db: Session, source: Source, run: CollectorRun, request: Request, response: Response | None
    ) -> None:
        assert db is session and request.mode == "live"
        order.append("before" if response is None else "after")
        if response is None:
            source.config = {"quota": source.config.get("quota", 0) + 1}

    responses.side_effect = response
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        adapter,
        [Target("catalog", "a", [Request()])],
        settings=settings,
        request_hook=hook,
    )
    assert run.status == "success" and run.http_requests == 2
    assert clock.waits == [120]
    assert order == ["before", "fetch", "after"] * 2
    assert not any(active for _, active in calls)


def test_block_count_resets_only_on_live_nonblock_response(
    session: Session, settings: Settings, network: Network
) -> None:
    adapter, responses, _ = network
    responses.side_effect = [Response(b"block", 429), Response(b"ok", 200), Response(b"block", 430)]
    for request, expected in [
        (Request(), 1),
        (Request(mode="csv", body=b"ok"), 1),
        (Request(), 0),
        (Request(), 1),
    ]:
        run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        execute_run(
            session, run.id, adapter, [Target("catalog", "a", [request])], settings=settings
        )
        assert session.get_one(Source, 1).consecutive_block_count == expected


@pytest.mark.parametrize(
    "cap,budget,error", [(60, 300, "retry_not_before"), (600, 60, "wall_time_budget")]
)
def test_503_wait_respects_configured_cap_and_plan_budget(
    session: Session,
    settings: Settings,
    network: Network,
    clock: Clock,
    cap: int,
    budget: int,
    error: str,
) -> None:
    adapter, responses, _ = network
    settings.collector_retry_wait_cap_seconds = cap
    responses.return_value = Response(b"busy", 503, headers={"Retry-After": "120"})
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        adapter,
        [Target("catalog", "a", [Request()])],
        settings=settings,
        wall_time_seconds=budget,
    )
    assert run.status == "partial" and run.error_message == error
    assert responses.call_count == 1 and not clock.waits


@pytest.mark.parametrize("header", ["garbage", "-1", "1.5", ""])
def test_invalid_retry_after_is_ignored(header: str) -> None:
    assert (
        lifecycle._retry_after(Response(None, 503, headers={"Retry-After": header}), Clock.now)
        is None
    )
