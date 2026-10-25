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
from pulso_workers import ops, schedules, tasks
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


def test_before_daily_slot_keeps_overdue_without_historical_catchup(
    session: Session,
    recovery: Mock,
) -> None:
    recovery.now.return_value = NOW.replace(hour=16)
    ops.heartbeat()
    session.expire_all()
    assert session.get_one(Source, 1).status == "overdue"
    assert not session.scalars(select(CollectorRun)).all()
    assert not session.scalars(select(CollectionGap)).all()


@pytest.mark.parametrize("audit_first", [True, False])
def test_slot_grace_leaves_scheduled_failure_one_catchup(
    session: Session, recovery: Mock, audit_first: bool
) -> None:
    due = NOW.replace(hour=17)
    recovery.now.return_value = due
    if audit_first:
        ops.heartbeat()
        assert not session.scalars(select(CollectorRun)).all()
        session.expire_all()
        assert session.get_one(Source, 1).status == "active"
    tasks.enqueue_scheduled("fx_frankfurter", "fx", "daily")
    scheduled = session.scalars(select(CollectorRun)).one()
    assert (scheduled.trigger, scheduled.status) == ("schedule", "queued")
    scheduled.status = "failed"
    session.commit()
    recovery.now.return_value = due + ops.OFFLINE_AFTER - timedelta(seconds=1)
    ops.heartbeat()
    assert len(session.scalars(select(CollectorRun)).all()) == 1
    session.expire_all()
    assert session.get_one(Source, 1).status == "active"
    for minutes in (15, 30, 45, 60):
        recovery.now.return_value = due + timedelta(minutes=minutes)
        ops.heartbeat()
        session.expire_all()
        catchup = session.scalars(
            select(CollectorRun).where(CollectorRun.trigger == "catchup")
        ).one()
        assert catchup.slot_key == scheduled.slot_key == "fx:2026-10-22"
        assert catchup.status == ("queued" if minutes == 15 else "failed")
        catchup.status = "failed"
        session.commit()
    assert len(session.scalars(select(CollectorRun)).all()) == 2


@pytest.mark.parametrize(
    "freight_catchup,today",
    [
        (None, False),
        ("failed", False),
        ("skipped", False),
        ("partial", False),
        ("success", False),
        ("failed", True),
    ],
)
def test_spent_weekly_catchup_does_not_block_daily_slot(
    session: Session,
    recovery: Mock,
    monkeypatch: pytest.MonkeyPatch,
    freight_catchup: str | None,
    today: bool,
) -> None:
    # The weekly CJ freight slot is unscheduled until it has a plan (DEC-321b).
    slots = (*schedules.COLLECTION_SLOTS, ("cj", "freight", 30, 4, "1"))
    monkeypatch.setattr(ops, "COLLECTION_SLOTS", slots)
    session.get_one(Source, 1).key = "cj"
    monday = NOW.replace(day=19, hour=4, minute=30)
    session.add(
        CollectorRun(
            source_id=1,
            trigger="schedule",
            slot_key="freight:2026-W43",
            status="success" if freight_catchup is None else "failed",
            complete=freight_catchup is None,
            queued_at=monday,
        )
    )
    if freight_catchup is not None:
        session.add(
            CollectorRun(
                source_id=1,
                trigger="catchup",
                slot_key="freight:2026-W43",
                status=freight_catchup,
                queued_at=(NOW.replace(hour=4) if today else monday) + timedelta(minutes=15),
            )
        )
    session.add(
        CollectorRun(
            source_id=1,
            trigger="schedule",
            slot_key="catalog:2026-10-22",
            status="failed",
            queued_at=NOW.replace(hour=4),
        )
    )
    session.commit()
    for hour in (5, 6, 12, 23):
        recovery.now.return_value = NOW.replace(hour=hour)
        ops.heartbeat()
        session.expire_all()
        catchup = session.scalars(
            select(CollectorRun).where(
                CollectorRun.trigger == "catchup", CollectorRun.slot_key == "catalog:2026-10-22"
            )
        ).one_or_none()
        if today:
            assert catchup is None
            continue
        assert catchup is not None
        assert catchup.status == ("queued" if hour == 5 else "failed")
        catchup.status = "failed"
        session.commit()


@pytest.mark.parametrize(
    "earlier,latest,caught_up",
    [
        (None, "partial", False),
        ("failed", "partial", False),
        ("partial", "failed", True),
        ("partial", "skipped", True),
        ("success", "failed", False),
    ],
)
def test_latest_partial_slot_is_not_replanned(
    session: Session, recovery: Mock, earlier: str | None, latest: str, caught_up: bool
) -> None:
    session.get_one(Source, 1).key = "google_trends"
    recovery.now.return_value = datetime(2026, 11, 2, 6, tzinfo=UTC)
    for status in (earlier, latest):
        if status is not None:
            session.add(
                CollectorRun(
                    source_id=1,
                    trigger="schedule",
                    slot_key="trends:2026-W45",
                    status=status,
                    complete=status == "success",
                    queued_at=recovery.now.return_value - timedelta(hours=1),
                )
            )
            session.commit()
    ops.heartbeat()
    session.expire_all()
    scheduled = session.scalars(
        select(CollectorRun).where(CollectorRun.trigger == "schedule").order_by(CollectorRun.id)
    ).all()
    assert [run.status for run in scheduled] == [s for s in (earlier, latest) if s is not None]
    assert (
        bool(session.scalar(select(CollectorRun.id).where(CollectorRun.trigger == "catchup")))
        == caught_up
    )


def test_catchup_delivery_starts_after_audit_releases_source_lock(
    session: Session, recovery: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: set[int] = set()

    class Lock:
        def __init__(self, key: int) -> None:
            self.key, self.mine = key, False

        def acquire(self) -> bool:
            if self.key in held:
                return False
            held.add(self.key)
            self.mine = True
            return True

        def close(self) -> None:
            if self.mine:
                held.remove(self.key)
                self.mine = False

    def deliver(name: str, *, args: list[int], **kwargs: object) -> None:
        if "countdown" not in kwargs:
            session.expire_all()
            assert session.get_one(CollectorRun, args[0]).status == "queued"
            tasks.collect_run(args[0])

    monkeypatch.setattr(ops, "AdvisoryLock", Lock)
    monkeypatch.setattr(tasks, "AdvisoryLock", Lock)
    monkeypatch.setitem(tasks.PLANS, "fx_frankfurter", lambda *_: tasks.Plan(Mock(), [], 10))
    publisher = Mock(side_effect=deliver)
    monkeypatch.setattr(app, "send_task", publisher)
    session.add(
        CollectorRun(
            source_id=1,
            trigger="schedule",
            slot_key="fx:2026-10-22",
            status="failed",
            queued_at=NOW.replace(hour=17),
        )
    )
    session.commit()
    recovery.now.return_value = NOW.replace(hour=17, minute=15)
    ops.heartbeat()
    run = session.scalars(select(CollectorRun).where(CollectorRun.trigger == "catchup")).one()
    publisher.assert_called_once_with("collect.run", args=[run.id], queue="collect", retry=False)
    assert run.started_at is not None and "lock_retries" not in run.params
    assert not held


def test_catchup_publish_error_does_not_overwrite_started_delivery(
    session: Session, recovery: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def publish(run_id: int) -> None:
        run = session.get_one(CollectorRun, run_id)
        run.status, run.started_at = "running", NOW
        session.commit()
        raise ConnectionError("fixture-broker-secret")

    monkeypatch.setattr(ops, "publish_run", publish)
    ops.heartbeat()
    session.expire_all()
    run = session.scalars(select(CollectorRun)).one()
    assert (run.status, run.error_code, run.finished_at) == ("running", None, None)


def test_disabled_source_reconciles_but_cannot_catch_up(session: Session, recovery: Mock) -> None:
    source = session.get_one(Source, 1)
    source.enabled, source.status = False, "blocked"
    run = CollectorRun(
        source_id=1,
        trigger="manual",
        status="running",
        queued_at=NOW - timedelta(hours=3),
        started_at=NOW - timedelta(hours=3),
    )
    session.add(run)
    session.commit()
    ops.heartbeat()
    session.expire_all()
    assert (run.status, run.error_code) == ("failed", "abandoned")
    assert not source.enabled and source.status == "blocked"
    assert len(session.scalars(select(CollectorRun)).all()) == 1
    assert not session.scalars(select(CollectionGap)).all()


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
    if queue == "ops":  # A backlog after an ops outage expires instead of replaying audits.
        app.send_task.assert_called_once_with(
            "ops.heartbeat", queue="ops", retry=False, expires=300
        )


def test_sunday_crontab_slot_is_audited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Celery's day_of_week "0" is Sunday; ISO weekday numbers Sunday 7.
    monkeypatch.setattr(ops, "COLLECTION_SLOTS", (("fixture", "weekly", 0, 5, "0"),))
    monday = datetime(2026, 10, 19, tzinfo=UTC)
    due = [at for _, at in ops.slots("fixture", monday, monday + timedelta(days=7))]
    assert due == [datetime(2026, 10, 25, 5, tzinfo=UTC)]


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
