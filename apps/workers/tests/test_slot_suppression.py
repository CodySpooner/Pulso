import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.logging import JsonFormatter
from pulso_core.models import CollectorRun, Source
from pulso_sources.framework import enqueue_run
from pulso_workers import ops, tasks
from pulso_workers.celery_app import app

NOW = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)


@pytest.fixture
def clock(session: Session, monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW
    monkeypatch.setattr(tasks, "datetime", clock)
    return clock


def test_w2_busy_delivery_records_suppression_then_allows_later_slot(
    session: Session,
    clock: Mock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=False)))
    manual = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    manual.queued_at = NOW - timedelta(minutes=10)
    manual.params = {"private": "fixture-secret"}
    session.commit()
    tasks.collect_run(manual.id)
    session.refresh(manual)
    assert manual.status == "queued" and manual.params["lock_retries"] == 1
    app.send_task.reset_mock()
    caplog.set_level(logging.INFO, logger="pulso.workers")

    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    skipped = session.scalars(select(CollectorRun).where(CollectorRun.id != manual.id)).one()
    assert (skipped.status, skipped.slot_key, skipped.complete) == (
        "skipped",
        "catalog:2026-10-26",
        False,
    )
    assert skipped.params == {"blocked_by": manual.id}
    assert skipped.error_code == "slot_suppressed" and skipped.finished_at is not None
    app.send_task.assert_not_called()
    logs = "\n".join(JsonFormatter().format(record) for record in caplog.records)
    for value in ("slot_suppressed", "fixture", "catalog:2026-10-26", "600", str(manual.id)):
        assert value in logs
    assert "fixture-secret" not in logs

    clock.now.return_value = NOW + timedelta(days=30)
    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    queued = session.scalars(
        select(CollectorRun).where(CollectorRun.slot_key == "catalog:2026-11-25")
    ).one()
    app.send_task.assert_called_once_with(
        "collect.run", args=[queued.id], queue="collect", retry=False
    )
    session.refresh(manual)
    assert manual.status == "queued"  # Only the lock-fenced audit may abandon it.


def test_w2b_catalog_does_not_drop_weekly_freight_and_delivery_waits(
    session: Session, clock: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.get_one(Source, 1).key = "cj"
    session.add(
        CollectorRun(
            source_id=1,
            trigger="schedule",
            status="running",
            slot_key="catalog:2026-10-26",
            started_at=NOW - timedelta(minutes=30),
        )
    )
    session.commit()
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=False)))
    tasks.enqueue_scheduled("cj", "freight", "weekly")
    freight = session.scalars(
        select(CollectorRun).where(CollectorRun.slot_key == "freight:2026-W44")
    ).one()
    assert freight.status == "queued"
    app.send_task.assert_called_once_with(
        "collect.run", args=[freight.id], queue="collect", retry=False
    )
    for attempt in range(3):
        tasks.collect_run(freight.id)
        session.refresh(freight)
        assert freight.status == ("queued" if attempt < 2 else "failed")
    assert freight.error_code == "source_lock_busy" and freight.params["lock_retries"] == 2
    assert app.send_task.call_count == 3


@pytest.mark.parametrize("status", ["queued", "running"])
@pytest.mark.parametrize("age_seconds", [7199, 7200, 7201])
def test_stale_rows_never_block_at_recovery_threshold(
    session: Session, clock: Mock, status: str, age_seconds: int
) -> None:
    run = CollectorRun(
        source_id=1,
        trigger="schedule",
        status=status,
        slot_key="catalog:2026-10-25",
        queued_at=NOW - timedelta(days=1)
        if status == "running"
        else NOW - timedelta(seconds=age_seconds),
        started_at=NOW - timedelta(seconds=age_seconds) if status == "running" else None,
    )
    session.add(run)
    session.commit()
    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    scheduled = session.scalars(
        select(CollectorRun).where(CollectorRun.slot_key == "catalog:2026-10-26")
    ).one()
    assert scheduled.status == ("skipped" if age_seconds < 7200 else "queued")
    assert app.send_task.call_count == int(age_seconds >= 7200)
    session.refresh(run)
    assert run.status == status


@pytest.mark.parametrize(
    "source_key,job", [("cj", "catalog"), ("google_trends", "trends"), ("fx_frankfurter", "fx")]
)
def test_manual_default_job_suppression_remains_missing_for_gap_audit(
    session: Session, clock: Mock, source_key: str, job: str
) -> None:
    source = session.get_one(Source, 1)
    source.key = source_key
    run = CollectorRun(source_id=1, trigger="manual", status="running", started_at=NOW)
    session.add(run)
    session.commit()
    clock.now.return_value = NOW.replace(hour=18)
    # The run is recent at the scheduled enqueue, regardless of the source's due hour.
    run.started_at = clock.now.return_value - timedelta(minutes=1)
    session.commit()
    tasks.enqueue_scheduled(source_key, job, "weekly" if job == "trends" else "daily")
    skipped = session.scalars(select(CollectorRun).where(CollectorRun.id != run.id)).one()
    assert skipped.status == "skipped" and skipped.params["blocked_by"] == run.id
    assert skipped.slot_key in ops.audit_slots(session, source, clock.now.return_value, None)
    session.refresh(source)
    assert source.status == "overdue"


def test_other_source_active_run_does_not_suppress(session: Session, clock: Mock) -> None:
    session.add(Source(id=2, key="other", name="Other", type="api", phase=1, enabled=True))
    session.add(CollectorRun(source_id=2, trigger="manual", status="running", started_at=NOW))
    session.commit()
    tasks.enqueue_scheduled("fixture", "catalog", "daily")
    assert app.send_task.call_count == 1
