from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from celery.exceptions import SoftTimeLimitExceeded  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.logging import JsonFormatter
from pulso_core.models import CollectorRun, RawPayload, Source
from pulso_sources import storage
from pulso_sources.framework import Request, Target, enqueue_run, lifecycle
from pulso_sources.framework import fetch as framework_fetch
from pulso_workers import tasks
from pulso_workers.beat import LockedScheduler
from pulso_workers.celery_app import app


@pytest.mark.parametrize("existing", [None, "queued", "running", "success", "disabled", "off"])
def test_scheduled_enqueue_is_gated_and_commits_before_publish(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    existing: str | None,
) -> None:
    monkeypatch.setenv("PULSO_SCHEDULER", "off" if existing == "off" else "on")
    if existing == "disabled":
        session.get_one(Source, 1).enabled = False
    elif existing in {"queued", "running", "success"}:
        session.add(
            CollectorRun(
                source_id=1,
                trigger="schedule",
                status=existing,
                slot_key=f"catalog:{datetime.now(UTC).date()}",
            )
        )
    session.commit()

    def publish(run_id: int) -> None:
        session.expire_all()
        run = session.get_one(CollectorRun, run_id)
        assert run.status == "queued" and run.started_at is None
        assert run.slot_key == f"catalog:{datetime.now(UTC).date()}"

    publisher = Mock(side_effect=publish)
    monkeypatch.setattr(tasks, "publish_run", publisher)
    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    assert publisher.call_count == int(existing is None)


def test_publish_failure_does_not_leak_into_json_logs(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    monkeypatch.setattr(
        app, "send_task", Mock(side_effect=ConnectionError("fixture-broker-secret"))
    )
    scheduler = LockedScheduler(app=app, lazy=True)
    scheduler.apply_entry(Mock(args=("fixture", "catalog", "daily")))
    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "fixture-broker-secret" not in logs and "ConnectionError" in logs
    run = session.scalars(select(CollectorRun)).one()
    assert (run.status, run.error_code, run.error_message) == (
        "failed",
        "publish_failed",
        "Publish failed",
    )


def test_scheduled_enqueue_persists_while_source_execution_lock_is_busy(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    lock = Mock(acquire=Mock(return_value=False))
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: lock)
    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    run = session.scalars(select(CollectorRun)).one()
    assert run.status == "queued"
    app.send_task.assert_called_once_with(
        "collect.run", args=[run.id], queue="collect", retry=False
    )
    lock.acquire.assert_not_called()


@pytest.mark.parametrize("locked", [False, True])
def test_consumer_locks_then_runs_and_stops_on_soft_limit(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    locked: bool,
) -> None:
    lock = Mock()
    lock.acquire.return_value = locked
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: lock)
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    targets = [Target("catalog", str(i), [Request(mode="fixture", body=b"data")]) for i in range(2)]
    adapter = Mock()
    adapter.parse.side_effect = SoftTimeLimitExceeded("fixture-soft-secret")
    monkeypatch.setitem(tasks.PLANS, "fixture", lambda *_: tasks.Plan(adapter, targets, 10))
    captured = Mock(return_value=RawPayload(id=1))
    monkeypatch.setattr(storage, "store_capture", captured)
    monkeypatch.setattr(storage, "read_capture", lambda _: b"data")

    def fetch(*args: object, **kwargs: object) -> object:
        session.expire_all()
        assert session.get_one(CollectorRun, run.id).status == "running"
        return framework_fetch(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(lifecycle, "fetch", fetch)
    tasks.collect_run(run.id)
    session.expire_all()
    assert run.status == ("partial" if locked else "queued")
    assert captured.call_count == int(locked)
    if locked:
        assert run.error_message == "SoftTimeLimitExceeded"
    lock.close.assert_called_once()
