"""Queued-run delivery. Adapter lanes register plans; unavailable adapters fail closed."""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from celery.exceptions import SoftTimeLimitExceeded  # type: ignore[import-untyped]
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pulso_core.db import get_session
from pulso_core.logging import job_id
from pulso_core.models import CollectorRun, Source
from pulso_core.settings import Settings, get_settings
from pulso_sources.framework import Adapter, RequestHook, Target, enqueue_run, execute_run, slot_key
from pulso_workers.celery_app import app
from pulso_workers.locks import AdvisoryLock

logger = logging.getLogger("pulso.workers")
StopExceptions = tuple[type[BaseException], ...]


@dataclass(frozen=True)
class Plan:
    adapter: Adapter[Any]
    targets: Sequence[Target]
    wall_time_seconds: int
    request_hook: RequestHook | None = None
    collector_max_retries: int | None = None
    finalize: Callable[[Session, CollectorRun], None] | None = None
    # A source-owned wrapper around execute_run (CJ: guarded transport, points, blocks).
    collect: Callable[[Session, int, Settings, StopExceptions], CollectorRun] | None = None


class UnknownJob(ValueError):
    """A factory's refusal of the run's job, stored as `unknown_job`."""


class PreRunFailed(Exception):
    """A refusal before execute_run. Code and message are fixed text: no settings or keys."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


PLANS: dict[str, Callable[[Session, Source, str], Plan]] = {}


def publish_run(run_id: int) -> None:
    app.send_task("collect.run", args=[run_id], queue="collect", retry=False)


def stale_after(source_key: str) -> timedelta:
    settings = get_settings()
    budget = {
        "shopify_stores": settings.shopify_wall_time_seconds,
        "cj": settings.cj_wall_time_seconds,
        "google_trends": settings.trends_wall_time_seconds,
        "fx_frankfurter": settings.fx_wall_time_seconds,
    }.get(source_key, settings.collector_wall_time_seconds)
    return max(timedelta(hours=2), timedelta(seconds=2 * budget))


def run_job(source_key: str, slot: str | None) -> str:
    return (
        slot.split(":", 1)[0]
        if slot
        else {"google_trends": "trends", "fx_frankfurter": "fx", "listing_images": "images"}.get(
            source_key, "catalog"
        )
    )


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
        # Serialize enqueue decisions with catch-up without taking the execution lock.
        source = session.scalar(
            select(Source).where(Source.key == source_key, Source.enabled).with_for_update()
        )
        if source is None:
            return
        now = datetime.now(UTC)
        slot = slot_key(job, now, cadence=cadence)
        if session.scalar(
            select(CollectorRun.id)
            .where(
                CollectorRun.source_id == source.id,
                CollectorRun.slot_key == slot,
                CollectorRun.status == "success",
            )
            .limit(1)
        ):
            return
        for run in session.scalars(
            select(CollectorRun)
            .where(
                CollectorRun.source_id == source.id,
                CollectorRun.status.in_(["queued", "running"]),
                func.coalesce(CollectorRun.started_at, CollectorRun.queued_at)
                > now - stale_after(source.key),
            )
            .order_by(CollectorRun.id)
        ):
            if run_job(source.key, run.slot_key) != job:
                continue
            age = (now - (run.started_at or run.queued_at).replace(tzinfo=UTC)).total_seconds()
            session.add(
                CollectorRun(
                    source_id=source.id,
                    trigger="schedule",
                    slot_key=slot,
                    status="skipped",
                    queued_at=now,
                    finished_at=now,
                    params={"blocked_by": run.id},
                    error_code="slot_suppressed",
                )
            )
            session.commit()
            # The shared JSON formatter omits extras; keep safe fields in the message.
            logger.info(
                "slot_suppressed source=%s job=%s slot_key=%s blocked_by=%s age_seconds=%s",
                source_key,
                job,
                slot,
                run.id,
                age,
            )
            return
        try:
            enqueue_run(
                session, source_id=source.id, trigger="schedule", slot_key=slot, publish=publish_run
            )
        except Exception as exc:
            logger.error("run_publish_failed", extra={"error_type": type(exc).__name__})


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
                raise PreRunFailed("source_unavailable", "Source disabled or adapter unavailable")
            job = run_job(source.key, run.slot_key)
            try:
                plan = PLANS[source.key](session, source, job)
            except UnknownJob:
                raise PreRunFailed("unknown_job", "Source has no plan for this job") from None
            except Exception as exc:
                raise PreRunFailed("plan_failed", f"Plan failed: {type(exc).__name__}") from None
            if not 0 < plan.wall_time_seconds < get_settings().collect_soft_time_limit_seconds:
                raise PreRunFailed(
                    "plan_budget_invalid", "Plan budget must be positive and below soft limit"
                )
            session.commit()
            settings = get_settings()
            if plan.collector_max_retries is not None:
                settings = settings.model_copy(
                    update={"collector_max_retries": plan.collector_max_retries}
                )
            stop: StopExceptions = (SoftTimeLimitExceeded,)
            if plan.collect is not None:
                result = plan.collect(session, run_id, settings, stop)
            else:
                result = execute_run(
                    session,
                    run_id,
                    plan.adapter,
                    plan.targets,
                    settings=settings,
                    wall_time_seconds=plan.wall_time_seconds,
                    request_hook=plan.request_hook,
                    stop_exceptions=stop,
                )
            if plan.finalize is not None:
                plan.finalize(session, result)
        except Exception as exc:
            session.rollback()
            code = exc.code if isinstance(exc, PreRunFailed) else type(exc).__name__
            session.execute(
                update(CollectorRun)
                .where(
                    CollectorRun.id == run_id,
                    CollectorRun.status.in_(["queued", "running"] if acquired else ["queued"]),
                )
                .values(
                    status="failed",
                    finished_at=datetime.now(UTC),
                    error_code=code,
                    error_message=str(exc) if isinstance(exc, PreRunFailed) else code,
                )
            )
            session.commit()
            logger.error("collection_failed", extra={"error_type": code})
        finally:
            lock.close()


app.task(name="collect.run")(collect_run)
