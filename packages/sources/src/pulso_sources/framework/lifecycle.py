"""Committed run/target evidence; scheduler owns the per-source lock (P1-04)."""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import (
    Adapter,
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    fetch,
)


class RunDeferred(RuntimeError):
    pass


class ResponseFailed(RuntimeError):
    pass


def enqueue_run(
    session: Session,
    *,
    source_id: int,
    trigger: str,
    publish: Callable[[int], object],
    slot_key: str | None = None,
) -> CollectorRun:
    """Commit queued evidence before publish; broker failure is recorded, never hidden."""
    run = CollectorRun(
        source_id=source_id,
        trigger=trigger,
        slot_key=slot_key,
        queued_at=datetime.now(UTC),
        status="queued",
    )
    session.add(run)
    session.commit()
    try:
        publish(run.id)
    except Exception:
        session.execute(
            update(CollectorRun)
            .where(CollectorRun.id == run.id, CollectorRun.status == "queued")
            .values(
                status="failed",
                error_code="publish_failed",
                error_message="Publish failed",
                finished_at=datetime.now(UTC),
            )
        )
        session.commit()
        raise
    return run


def _capture[R](
    session: Session,
    run: CollectorRun,
    source: Source,
    adapter: Adapter[R],
    request: Request,
    settings: Settings,
    deadline: float,
) -> tuple[Response, RawPayload]:
    if request.raw_payload_id is not None:
        if request.mode not in {"csv", "json", "fixture"}:
            raise ValueError("Existing raw captures require an offline request")
        if time.monotonic() >= deadline:
            raise RunDeferred("wall_time_budget")
        payload = session.get_one(RawPayload, request.raw_payload_id)
        if payload.source_id != run.source_id or payload.storage_key is None:
            raise ValueError("Existing raw capture must belong to the source and have a body")
        return Response(None, payload.status_code, payload.content_type, payload.etag), payload
    for attempt in range(settings.collector_max_retries + 1):
        if time.monotonic() >= deadline:
            raise RunDeferred("wall_time_budget")
        session.refresh(source)
        if request.mode == "live":
            if not source.enabled:
                raise RunDeferred("source_disabled")
            if source.retry_not_before and source.retry_not_before > datetime.now(UTC):
                raise RunDeferred("retry_not_before")
        try:
            run.http_requests += int(request.mode == "live")
            response = fetch(adapter, request, settings=settings)
        except TimeoutError, ConnectionError:
            session.commit()
            if attempt == settings.collector_max_retries:
                raise
        else:
            payload = storage.store_capture(
                session,
                source_id=source.id,
                source_key=source.key,
                run_id=run.id,
                body=response.body,
                content_type=response.content_type,
                status_code=response.status_code,
                etag=response.etag,
                request=request.params,
                captured_at=datetime.now(UTC),
            )
            run.last_status_code = response.status_code
            if request.mode == "live":
                source.last_status_code = response.status_code
            session.commit()
            if (
                response.status_code not in {500, 502, 503, 504}
                or attempt == settings.collector_max_retries
            ):
                return response, payload
        delay = min(
            settings.collector_backoff_base_seconds * 4**attempt,
            settings.collector_backoff_cap_seconds,
        )
        if time.monotonic() + delay >= deadline:
            raise RunDeferred("wall_time_budget")
        time.sleep(delay)
    raise AssertionError("Retry loop exhausted")


def execute_run[R](
    session: Session,
    run_id: int,
    adapter: Adapter[R],
    targets: Sequence[Target],
    *,
    settings: Settings,
    wall_time_seconds: int | None = None,
) -> CollectorRun:
    """Consume a queued run once, committing raw captures and each parsed payload.

    Target request iterables may page lazily, but all target identities must be planned
    up front. Adapters never commit. Error messages omit exception text (may hold secrets).
    """
    budget = (
        settings.collector_wall_time_seconds if wall_time_seconds is None else wall_time_seconds
    )
    if budget <= 0:
        raise ValueError("Wall-time budget must be positive")
    identities = [(target.scope, target.target_id) for target in targets]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate target identities")
    run = session.scalar(
        update(CollectorRun)
        .where(CollectorRun.id == run_id, CollectorRun.status == "queued")
        .values(status="running", started_at=datetime.now(UTC))
        .returning(CollectorRun)
    )
    session.commit()
    if run is None:
        existing = session.get(CollectorRun, run_id)
        if existing is None:
            raise ValueError("Unknown collector run")
        return existing
    source = session.get_one(Source, run.source_id)
    if run.trigger in {"schedule", "catchup"} and session.scalar(
        select(CollectorRun.id)
        .where(
            CollectorRun.source_id == run.source_id,
            CollectorRun.slot_key == run.slot_key,
            CollectorRun.status == "success",
            CollectorRun.trigger.in_(["schedule", "catchup"]),
        )
        .limit(1)
    ):
        run.status, run.finished_at = "skipped", datetime.now(UTC)
        session.commit()
        return run
    evidence = [
        CollectorRunTarget(
            run_id=run.id,
            scope=t.scope,
            target_id=t.target_id,
            status="pending",
            captured_at=datetime.now(UTC),
        )
        for t in targets
    ]
    session.add_all(evidence)
    session.commit()
    deadline = time.monotonic() + budget
    stopped = False
    guard_error = None
    for target, result in zip(targets, evidence, strict=True):
        complete = True
        try:
            if stopped:
                raise RunDeferred("run_stopped")
            for request in target.requests:
                response, payload = _capture(
                    session, run, source, adapter, request, settings, deadline
                )
                result.raw_payload_id = payload.id
                session.commit()
                if response.status_code is not None and not (
                    200 <= response.status_code < 300 or response.status_code == 304
                ):
                    raise ResponseFailed(f"http_{response.status_code}")
                complete = complete and response.complete
                if response.status_code != 304:
                    records = adapter.parse(storage.read_capture(payload))
                    stats = adapter.upsert(
                        session, records, payload, parser_version=adapter.parser_version
                    )
                    run.rows_fetched += len(records)
                    run.rows_inserted += stats.inserted
                    run.rows_updated += stats.updated
                    run.rows_unchanged += stats.unchanged
                    session.commit()
            result.status = (
                "success" if complete and result.raw_payload_id is not None else "partial"
            )
        except Exception as exc:
            session.rollback()
            result.status = "partial" if result.raw_payload_id is not None else "failed"
            if not stopped:
                run.error_code = type(exc).__name__
                run.error_message = (
                    str(exc)
                    if isinstance(exc, (RunDeferred, ResponseFailed))
                    else type(exc).__name__
                )
            if isinstance(exc, (RunDeferred, CollectorsLiveDisabled)):
                stopped = True
                result.status = "partial"
            if isinstance(exc, CollectorsLiveDisabled):
                guard_error = exc
        result.captured_at = datetime.now(UTC)
        session.commit()
    run.complete = bool(evidence) and all(t.status == "success" for t in evidence)
    run.status = (
        "success"
        if run.complete
        else "partial"
        if any(t.status in {"success", "partial"} for t in evidence)
        else "failed"
    )
    run.finished_at = datetime.now(UTC)
    session.commit()
    if guard_error:
        raise guard_error
    return run
