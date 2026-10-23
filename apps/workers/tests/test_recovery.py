from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from pulso_core.logging import JsonFormatter
from pulso_core.models import CollectionGap, CollectorRun, HostHeartbeat, Source
from pulso_sources.framework import lifecycle
from pulso_workers import ops, tasks
from pulso_workers.beat import LockedScheduler
from pulso_workers.celery_app import app

NOW = datetime(2026, 10, 22, 18, tzinfo=UTC)


@pytest.fixture
def recovery(session: Session, monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(ops, "datetime", clock)
    monkeypatch.setattr(tasks, "datetime", clock)
    monkeypatch.setattr(lifecycle, "datetime", clock)
    source = session.get_one(Source, 1)
    source.key, source.status = "fx_frankfurter", "active"
    session.add(HostHeartbeat(host="old-container", at=NOW - timedelta(hours=2)))
    session.commit()
    return clock


def test_two_hour_gap_and_restarts_are_idempotent(session: Session, recovery: Mock) -> None:
    for _ in range(3):
        app.tasks["ops.heartbeat"].run()
        app.tasks["audit.schedule"].run()
    session.expire_all()
    gap = session.scalars(select(CollectionGap)).one()
    assert (gap.reason, gap.slot_key) == ("host_offline", "fx:2026-10-22")
    assert session.get_one(Source, 1).status == "overdue"
    run = session.scalars(select(CollectorRun)).one()
    assert (run.trigger, run.status, run.slot_key) == ("catchup", "queued", gap.slot_key)
    assert len(session.scalars(select(HostHeartbeat)).all()) == 4
    app.send_task.assert_called_once_with(
        "collect.run", args=[run.id], queue="collect", retry=False
    )
    # Even a terminal catch-up is not repeatedly retried by the audit.
    run.status = "failed"
    session.commit()
    ops.heartbeat()
    assert len(session.scalars(select(CollectorRun)).all()) == 1


@pytest.mark.parametrize("status", ["queued", "running"])
@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("held", [False, True])
def test_reconciliation_requires_free_lock(
    session: Session,
    recovery: Mock,
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    stale: bool,
    held: bool,
) -> None:
    run = CollectorRun(
        source_id=1,
        trigger="manual",
        status=status,
        queued_at=NOW - timedelta(hours=3 if stale else 1),
        started_at=NOW - timedelta(hours=3 if stale else 1) if status == "running" else None,
    )
    session.add(run)
    session.commit()
    locks: dict[int, Mock] = {}

    def lock(key: int) -> Mock:
        locks[key] = Mock(acquire=Mock(return_value=key == -1 or not held))
        return locks[key]

    monkeypatch.setattr(ops, "AdvisoryLock", lock)
    ops.heartbeat()
    session.expire_all()
    assert run.status == ("failed" if stale and not held else status)
    assert run.error_code == ("abandoned" if stale and not held else None)
    assert len(session.scalars(select(CollectorRun)).all()) == (2 if stale and not held else 1)
    assert session.scalars(select(CollectionGap)).one().reason == "host_offline"
    for acquired in locks.values():
        acquired.close.assert_called_once()


def test_all_enabled_sources_get_one_catchup_and_disabled_internal_get_none(
    session: Session,
    recovery: Mock,
) -> None:
    session.add_all(
        [
            Source(id=2, key="shopify_stores", name="Shopify", type="api", phase=1, enabled=True),
            Source(id=3, key="cj", name="CJ", type="api", phase=1, enabled=False),
            Source(id=4, key="backup", name="Backup", type="internal", phase=1, enabled=True),
        ]
    )
    session.commit()
    ops.audit()
    ops.audit()
    runs = session.scalars(select(CollectorRun).order_by(CollectorRun.source_id)).all()
    assert [(r.source_id, r.slot_key) for r in runs] == [
        (1, "fx:2026-10-22"),
        (2, "catalog:2026-10-22"),
    ]
    assert not session.get_one(Source, 3).enabled


def test_success_fills_only_matching_gap_and_clears_overdue(
    session: Session, recovery: Mock
) -> None:
    ops.heartbeat()
    run = session.scalars(select(CollectorRun)).one()
    run.status, run.complete = "success", True
    session.commit()
    ops.audit()
    session.expire_all()
    assert session.scalars(select(CollectionGap)).one().filled_by_run_id == run.id
    assert session.get_one(Source, 1).status == "active"


def test_missed_days_record_gaps_without_backdated_catchup(
    session: Session, recovery: Mock
) -> None:
    recovery.now.return_value = NOW + timedelta(days=2)
    ops.heartbeat()
    gaps = session.scalars(select(CollectionGap)).all()
    assert len(gaps) == 3 and all(g.reason == "host_offline" for g in gaps)
    assert session.scalars(select(CollectorRun)).one().slot_key == "fx:2026-10-24"


def test_weekly_slot_catches_up_later_in_same_week_once(session: Session, recovery: Mock) -> None:
    source = session.get_one(Source, 1)
    source.key = "google_trends"
    session.commit()
    ops.audit()
    run = session.scalars(select(CollectorRun)).one()
    assert run.slot_key == "trends:2026-W43"
    run.status = "failed"
    session.commit()
    recovery.now.return_value = NOW + timedelta(days=1)
    ops.audit()
    assert len(session.scalars(select(CollectorRun)).all()) == 1


@pytest.mark.parametrize("boundary", ["catchup", "retry", "ops"])
def test_publish_boundaries_redact_exception_text(
    session: Session,
    recovery: Mock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    boundary: str,
) -> None:
    monkeypatch.setattr(
        app, "send_task", Mock(side_effect=ConnectionError("fixture-broker-secret"))
    )
    if boundary == "catchup":
        ops.heartbeat()
    elif boundary == "ops":
        LockedScheduler(app=app, lazy=True).apply_entry(Mock(task="ops.heartbeat"))
    else:
        run = lifecycle.enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=False)))
        tasks.collect_run(run.id)
    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    assert "fixture-broker-secret" not in logs and "ConnectionError" in logs
    if boundary != "ops":
        session.expire_all()
        run = session.scalars(select(CollectorRun)).one()
        assert (run.status, run.error_code, run.error_message) == (
            "failed",
            "publish_failed",
            "Publish failed",
        )


def test_busy_delivery_has_bounded_durable_retries(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=False)))
    run = lifecycle.enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    for attempt in range(3):
        tasks.collect_run(run.id)
        session.expire_all()
        assert run.params["lock_retries"] == min(attempt + 1, 2)
        assert run.status == ("queued" if attempt < 2 else "failed")
    assert run.error_code == "source_lock_busy" and run.finished_at is not None
    tasks.collect_run(run.id)
    assert app.send_task.call_count == 2
    assert all(call.kwargs["countdown"] == 900 for call in app.send_task.call_args_list)


@pytest.mark.parametrize("queue", ["ops", "collect"])
def test_only_ops_consumer_starts_recovery(
    session: Session,
    recovery: Mock,
    queue: str,
) -> None:
    ops.start_ops(Mock(task_consumer=Mock(queues=[SimpleNamespace(name=queue)])))
    assert app.send_task.call_count == int(queue == "ops")


@pytest.mark.parametrize("guard", ["flag", "worktree"])
def test_ops_guard_leaves_database_untouched(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    guard: str,
) -> None:
    monkeypatch.setenv("PULSO_SCHEDULER", "on" if guard == "worktree" else "off")
    monkeypatch.setattr(ops, "is_linked_worktree", lambda _: guard == "worktree")
    ops.heartbeat()
    assert not session.scalars(select(HostHeartbeat)).all()
    assert not session.scalars(select(CollectorRun)).all()


@pytest.mark.db
def test_real_source_lock_fences_stale_reconciliation(
    session: Session,
    recovery: Mock,
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pulso_workers import locks

    key = 65536 + uuid4().int % (2**31 - 65538)
    monkeypatch.setattr(locks, "get_engine", lambda: db_engine)
    monkeypatch.setattr(ops, "AdvisoryLock", lambda source: locks.AdvisoryLock(key + source))
    run = CollectorRun(
        source_id=1,
        trigger="manual",
        status="running",
        queued_at=NOW - timedelta(hours=3),
        started_at=NOW - timedelta(hours=3),
    )
    session.add(run)
    session.commit()
    live = locks.AdvisoryLock(key + 1)
    assert live.acquire()
    try:
        ops.audit()
        session.refresh(run)
        assert run.status == "running" and live.held()
        app.send_task.assert_not_called()
    finally:
        live.close()
    ops.audit()
    session.refresh(run)
    assert (run.status, run.error_code) == ("failed", "abandoned")
    assert app.send_task.call_count == 1
