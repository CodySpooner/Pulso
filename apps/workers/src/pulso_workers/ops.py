"""Offline evidence and bounded recovery, serialized on the separate ops consumer."""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from socket import gethostname
from typing import Any

from celery.signals import worker_ready  # type: ignore[import-untyped]
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pulso_core.db import get_session
from pulso_core.models import CollectionGap, CollectorRun, HostHeartbeat, Source
from pulso_core.settings import get_settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.framework import enqueue_run, slot_key
from pulso_workers.celery_app import app
from pulso_workers.locks import AdvisoryLock
from pulso_workers.schedules import COLLECTION_SLOTS
from pulso_workers.tasks import publish_run

logger = logging.getLogger("pulso.ops")
OFFLINE_AFTER = timedelta(minutes=15)


def slots(source_key: str, start: datetime, end: datetime) -> Iterator[tuple[str, datetime]]:
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= end:
        for source, job, minute, hour, weekday in COLLECTION_SLOTS:
            due = day.replace(hour=hour, minute=minute)
            if source == source_key and (weekday == "*" or day.isoweekday() == int(weekday)):
                if start <= due <= end:
                    yield slot_key(job, due, cadence="daily" if weekday == "*" else "weekly"), due
        day += timedelta(days=1)


def audit_slots(
    session: Session, source: Source, now: datetime, previous: datetime | None
) -> list[str]:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week = today - timedelta(days=today.weekday())
    offline = previous is not None and now - previous > OFFLINE_AFTER
    start = today - timedelta(days=7)
    if offline and previous is not None:
        start = min(previous, start)
    expected = list(slots(source.key, start, now))
    latest = {slot.split(":", 1)[0]: slot for slot, _ in expected}
    missing = []
    overdue = False
    for slot, due in expected:
        success = session.scalar(
            select(CollectorRun.id)
            .where(
                CollectorRun.source_id == source.id,
                CollectorRun.slot_key == slot,
                CollectorRun.status == "success",
                CollectorRun.complete,
            )
            .limit(1)
        )
        gap = session.scalar(
            select(CollectionGap).where(
                CollectionGap.source_id == source.id,
                CollectionGap.slot_key == slot,
            )
        )
        if success is not None:
            if gap is not None:
                gap.filled_by_run_id = success
            continue
        overdue |= latest[slot.split(":", 1)[0]] == slot
        if due >= today or ("-W" in slot and due >= week):
            missing.append(slot)
        if offline and previous is not None and due > previous and gap is None:
            day = due.replace(hour=0, minute=0, second=0, microsecond=0)
            session.add(
                CollectionGap(
                    source_id=source.id,
                    slot_key=slot,
                    slot_start=day,
                    slot_end=day + timedelta(days=1),
                    reason="host_offline",
                    detected_at=now,
                )
            )
    session.execute(
        update(Source)
        .where(Source.id == source.id, Source.enabled, Source.status != "blocked")
        .values(status="overdue" if overdue else "active")
    )
    session.commit()
    return missing


def recover_source(session: Session, source: Source, now: datetime, missing: list[str]) -> None:
    settings = get_settings()
    budget = {
        "shopify_stores": settings.shopify_wall_time_seconds,
        "cj": settings.cj_wall_time_seconds,
        "google_trends": settings.trends_wall_time_seconds,
        "fx_frankfurter": settings.fx_wall_time_seconds,
    }.get(source.key, settings.collector_wall_time_seconds)
    session.execute(
        update(CollectorRun)
        .where(
            CollectorRun.source_id == source.id,
            CollectorRun.status.in_(["queued", "running"]),
            func.coalesce(CollectorRun.started_at, CollectorRun.queued_at)
            <= now - max(timedelta(hours=2), timedelta(seconds=2 * budget)),
        )
        .values(
            status="failed",
            complete=False,
            finished_at=now,
            error_code="abandoned",
            error_message="abandoned",
        )
    )
    session.commit()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if (
        not source.enabled
        or not missing
        or session.scalar(
            select(CollectorRun.id)
            .where(
                CollectorRun.source_id == source.id,
                (CollectorRun.status.in_(["queued", "running"]))
                | ((CollectorRun.trigger == "catchup") & (CollectorRun.queued_at >= today))
                | (
                    (CollectorRun.slot_key == missing[0])
                    & ((CollectorRun.trigger == "catchup") | (CollectorRun.status == "success"))
                ),
            )
            .limit(1)
        )
    ):
        return
    try:
        enqueue_run(
            session,
            source_id=source.id,
            trigger="catchup",
            slot_key=missing[0],
            publish=publish_run,
        )
    except Exception as exc:
        logger.error("catchup_publish_failed", extra={"error_type": type(exc).__name__})


def audit(*, heartbeat: bool = False) -> None:
    if not get_settings().pulso_scheduler or is_linked_worktree(__file__):
        return
    # Separate from Beat (0) and every source (>0); protects heartbeat window consumption.
    lock = AdvisoryLock(-1)
    try:
        if not lock.acquire():
            return
        with get_session() as session:
            now = datetime.now(UTC)
            previous = session.scalar(select(func.max(HostHeartbeat.at)))
            if previous is not None:
                previous = previous.replace(tzinfo=UTC)
            for source in session.scalars(
                select(Source).where(
                    Source.type != "internal",
                    Source.key.in_({row[0] for row in COLLECTION_SLOTS}),
                )
            ):
                missing = audit_slots(session, source, now, previous) if source.enabled else []
                source_lock = AdvisoryLock(source.id)
                try:
                    if source_lock.acquire():
                        session.refresh(source)
                        recover_source(session, source, now, missing)
                finally:
                    source_lock.close()
            if heartbeat:
                session.add(HostHeartbeat(host=gethostname(), at=now))
                session.commit()
    finally:
        lock.close()


def heartbeat() -> None:
    audit(heartbeat=True)


def publish_ops(name: str) -> None:
    try:
        app.send_task(name, queue="ops", retry=False)
    except Exception as exc:
        logger.error("ops_publish_failed", extra={"error_type": type(exc).__name__})


def start_ops(sender: Any, **kwargs: object) -> None:
    if get_settings().pulso_scheduler and not is_linked_worktree(__file__):
        if any(queue.name == "ops" for queue in sender.task_consumer.queues):
            publish_ops("ops.heartbeat")


app.task(name="ops.heartbeat")(heartbeat)
app.task(name="audit.schedule")(audit)
worker_ready.connect(start_ops, weak=False)
