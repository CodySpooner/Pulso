import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    UpsertStats,
    enqueue_run,
    execute_run,
    lifecycle,
)


class FakeAdapter:
    parser_version = "1"

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise AssertionError("Offline adapter cannot fetch")

    def parse(self, body: bytes) -> Sequence[str]:
        if body == b"broken":
            raise ValueError("fixture-secret-must-not-leak")
        return body.decode().splitlines()

    def upsert(
        self, session: Session, records: Sequence[str], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        return UpsertStats(inserted=len(records))


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, CollectorRun, list[RawPayload]]:
    run = CollectorRun(
        id=1,
        source_id=1,
        trigger="csv",
        status="queued",
        queued_at=datetime.now(UTC) - timedelta(days=1),
        rows_fetched=0,
        rows_inserted=0,
        rows_updated=0,
        rows_unchanged=0,
        http_requests=0,
    )
    source = Source(id=1, key="fixture", enabled=True, consecutive_block_count=0)
    session = Mock(spec=Session)

    def claim(statement: object) -> CollectorRun | None:
        if run.status != "queued":
            return None
        run.status = "running"
        run.started_at = datetime.now(UTC)
        return run

    session.scalar.side_effect = claim
    session.get.return_value = run
    session.get_one.return_value = source
    captures: list[RawPayload] = []
    bodies: dict[int, bytes] = {}

    def store(_session: Session, **kwargs: Any) -> RawPayload:
        body = kwargs.pop("body")
        kwargs.pop("source_key")
        payload = RawPayload(id=len(captures) + 1, **kwargs)
        captures.append(payload)
        bodies[payload.id] = body
        return payload

    monkeypatch.setattr(storage, "store_capture", store)
    monkeypatch.setattr(storage, "read_capture", lambda payload: bodies[payload.id])
    return session, run, captures


def planned(*bodies: bytes) -> list[Target]:
    return [
        Target("catalog", str(i), [Request(mode="fixture", body=body)])
        for i, body in enumerate(bodies)
    ]


def test_queued_commit_precedes_publish_and_failure_is_durable() -> None:
    session = Mock(spec=Session)
    added: list[CollectorRun] = []
    session.add.side_effect = added.append

    def commit() -> None:
        added[0].id = 7

    session.commit.side_effect = commit

    def publish(run_id: int) -> None:
        assert run_id == 7
        assert session.commit.call_count == 1
        assert added[0].queued_at.tzinfo == UTC
        assert added[0].started_at is None
        assert added[0].status == "queued"
        raise RuntimeError("fixture-broker-secret")

    with pytest.raises(RuntimeError):
        enqueue_run(session, source_id=1, trigger="csv", publish=publish)
    update = session.execute.call_args.args[0].compile().params
    assert update["status"] == "failed"
    assert update["error_code"] == "publish_failed"
    assert "fixture-broker-secret" not in update["error_message"]
    assert session.commit.call_count == 2


def test_success_counts_times_and_late_delivery_noop(
    harness: tuple[Mock, CollectorRun, list[RawPayload]], settings: Settings
) -> None:
    session, run, captures = harness
    result = execute_run(session, 1, FakeAdapter(), planned(b"a\nb", b"a\nb"), settings=settings)
    assert result is run
    assert run.status == "success" and run.complete
    assert run.queued_at < run.started_at <= run.finished_at  # type: ignore[operator]
    assert (run.rows_fetched, run.rows_inserted, run.http_requests) == (4, 4, 0)
    assert len(captures) == 2 and captures[0].id != captures[1].id
    evidence: list[CollectorRunTarget] = session.add_all.call_args.args[0]
    assert all(t.status == "success" and t.captured_at > run.started_at for t in evidence)  # type: ignore[operator]
    execute_run(session, 1, FakeAdapter(), planned(b"unused"), settings=settings)
    assert len(captures) == 2


def test_304_and_failed_target_do_not_share_coverage(
    harness: tuple[Mock, CollectorRun, list[RawPayload]],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, captures = harness
    monkeypatch.setattr(
        lifecycle, "fetch", Mock(side_effect=[Response(None, 304), Response(b"broken", 200)])
    )
    execute_run(session, 1, FakeAdapter(), planned(b"", b""), settings=settings)
    evidence: list[CollectorRunTarget] = session.add_all.call_args.args[0]
    assert run.status == "partial" and not run.complete
    assert (run.rows_inserted, run.rows_fetched) == (0, 0)
    assert [t.status for t in evidence] == ["success", "partial"]
    assert [t.raw_payload_id for t in evidence] == [1, 2]
    assert len(captures) == 2
    assert run.error_message == "ValueError"


def test_request_retries_preserve_each_capture(
    harness: tuple[Mock, CollectorRun, list[RawPayload]],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, captures = harness
    monkeypatch.setattr(
        lifecycle, "fetch", Mock(side_effect=[Response(b"busy", 503)] * 3 + [Response(b"ok", 200)])
    )
    sleep = Mock()
    monkeypatch.setattr(time, "sleep", sleep)
    execute_run(session, 1, FakeAdapter(), planned(b""), settings=settings)
    assert [call.args[0] for call in sleep.call_args_list] == [2, 8, 30]
    assert [capture.status_code for capture in captures] == [503, 503, 503, 200]
    assert run.rows_inserted == 1 and run.status == "success"


def test_persisted_retry_deadline_prevents_later_request(
    harness: tuple[Mock, CollectorRun, list[RawPayload]],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, captures = harness
    session.get_one.return_value.retry_not_before = datetime.now(UTC) + timedelta(hours=2)
    network = Mock()
    monkeypatch.setattr(lifecycle, "fetch", network)
    execute_run(session, 1, FakeAdapter(), [Target("catalog", "a", [Request()])], settings=settings)
    network.assert_not_called()
    assert not captures and run.status == "partial"
    assert run.error_message == "retry_not_before"


def test_live_guard_is_raised_and_run_finished(
    harness: tuple[Mock, CollectorRun, list[RawPayload]], settings: Settings
) -> None:
    session, run, captures = harness
    with pytest.raises(CollectorsLiveDisabled):
        execute_run(
            session, 1, FakeAdapter(), [Target("catalog", "a", [Request()])], settings=settings
        )
    assert run.finished_at is not None
    assert not captures


def test_expired_budget_stops_all_targets(
    harness: tuple[Mock, CollectorRun, list[RawPayload]],
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, run, captures = harness
    monkeypatch.setattr(time, "monotonic", Mock(side_effect=[0, 2]))
    execute_run(
        session, 1, FakeAdapter(), planned(b"a", b"b"), settings=settings, wall_time_seconds=1
    )
    assert not captures and run.status == "partial"
    evidence: list[CollectorRunTarget] = session.add_all.call_args.args[0]
    assert [target.status for target in evidence] == ["partial", "partial"]
    assert run.error_message == "wall_time_budget"
