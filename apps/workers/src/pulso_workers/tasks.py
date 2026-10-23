"""Queued-run delivery. Adapter lanes register plans; unavailable adapters fail closed."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from celery.exceptions import SoftTimeLimitExceeded  # type: ignore[import-untyped]
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pulso_core.db import get_session
from pulso_core.logging import job_id
from pulso_core.models import CollectorRun, Source
from pulso_core.settings import get_settings
from pulso_sources.framework import Adapter, RequestHook, Target, enqueue_run, execute_run, slot_key
from pulso_workers.celery_app import app
from pulso_workers.locks import AdvisoryLock

logger = logging.getLogger("pulso.workers")


@dataclass(frozen=True)
class Plan:
    adapter: Adapter[Any]
    targets: Sequence[Target]
    wall_time_seconds: int
    request_hook: RequestHook | None = None


PLANS: dict[str, Callable[[Session, Source, str], Plan]] = {}


def publish_run(run_id: int) -> None:
    app.send_task("collect.run", args=[run_id], queue="collect", retry=False)


def defer_busy(session: Session, run_id: int) -> None:
    run = session.scalar(
        select(CollectorRun)
        .where(CollectorRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None or run.status != "queued":
        return
    retries = int(run.params.get("lock_retries", 0))
    settings = get_settings()
    if retries >= settings.collector_task_max_retries:
        run.status, run.finished_at = "failed", datetime.now(UTC)
        run.error_code = run.error_message = "source_lock_busy"
        session.commit()
        return
    run.params = {**run.params, "lock_retries": retries + 1}
    session.commit()
    try:
        app.send_task(
            "collect.run",
            args=[run_id],
            queue="collect",
            retry=False,
            countdown=settings.collector_task_retry_seconds,
        )
    except Exception as exc:
        session.execute(
            update(CollectorRun)
            .where(CollectorRun.id == run_id, CollectorRun.status == "queued")
            .values(
                status="failed",
                finished_at=datetime.now(UTC),
                error_code="publish_failed",
                error_message="Publish failed",
            )
        )
        session.commit()
        logger.error("retry_publish_failed", extra={"error_type": type(exc).__name__})


def enqueue_scheduled(source_key: str, job: str, cadence: Literal["daily", "weekly"]) -> None:
    if not get_settings().pulso_scheduler:
        return
    with get_session() as session:
        source = session.scalar(select(Source).where(Source.key == source_key, Source.enabled))
        if source is None:
            return
        lock = AdvisoryLock(source.id)
        try:
            if not lock.acquire():
                return
            session.refresh(source)
            if not source.enabled:
                return
            slot = slot_key(job, datetime.now(UTC), cadence=cadence)
            if session.scalar(
                select(CollectorRun.id)
                .where(
                    CollectorRun.source_id == source.id,
                    (CollectorRun.status.in_(["queued", "running"]))
                    | ((CollectorRun.slot_key == slot) & (CollectorRun.status == "success")),
                )
                .limit(1)
            ):
                return
            try:
                enqueue_run(
                    session,
                    source_id=source.id,
                    trigger="schedule",
                    slot_key=slot,
                    publish=publish_run,
                )
            except Exception as exc:
                logger.error("run_publish_failed", extra={"error_type": type(exc).__name__})
        finally:
            lock.close()


def collect_run(run_id: int) -> None:
    with job_id.set(str(run_id)), get_session() as session:
        run = session.get_one(CollectorRun, run_id)
        if run.status != "queued":
            return
        lock = AdvisoryLock(run.source_id)
        acquired = False
        try:
            acquired = lock.acquire()
            if not acquired:
                defer_busy(session, run_id)
                return
            session.refresh(run)
            if run.status != "queued":
                return
            source = session.get_one(Source, run.source_id)
            if not source.enabled or source.key not in PLANS:
                raise ValueError("Source disabled or adapter unavailable")
            job = (
                run.slot_key.split(":", 1)[0]
                if run.slot_key
                else {
                    "google_trends": "trends",
                    "fx_frankfurter": "fx",
                }.get(source.key, "catalog")
            )
            plan = PLANS[source.key](session, source, job)
            if not 0 < plan.wall_time_seconds < get_settings().collect_soft_time_limit_seconds:
                raise ValueError("Plan budget must be positive and below soft limit")
            session.commit()
            execute_run(
                session,
                run_id,
                plan.adapter,
                plan.targets,
                settings=get_settings(),
                wall_time_seconds=plan.wall_time_seconds,
                request_hook=plan.request_hook,
                stop_exceptions=(SoftTimeLimitExceeded,),
            )
        except Exception as exc:
            session.rollback()
            session.execute(
                update(CollectorRun)
                .where(
                    CollectorRun.id == run_id,
                    CollectorRun.status.in_(["queued", "running"] if acquired else ["queued"]),
                )
                .values(
                    status="failed",
                    finished_at=datetime.now(UTC),
                    error_code=type(exc).__name__,
                    error_message=type(exc).__name__,
                )
            )
            session.commit()
            logger.error(
                "collection_failed", extra={"run_id": run_id, "error_type": type(exc).__name__}
            )
        finally:
            lock.close()


app.task(name="collect.run")(collect_run)
