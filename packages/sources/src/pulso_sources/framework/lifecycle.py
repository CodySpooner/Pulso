"""Committed run/target evidence; scheduler owns the per-source lock (P1-04)."""

import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, Source, SourceEvent
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import (
    Adapter,
    CollectorsLiveDisabled,
    Request,
    RequestHook,
    Response,
    Target,
    fetch,
    require_live,
)

BLOCK_STATUSES = {403, 429, 430}
RETRY_STATUSES = {500, 502, 503, 504}


def _retry_after(response: Response, now: datetime) -> datetime | None:
    value = next((v.strip() for k, v in response.headers.items() if k.lower() == "retry-after"), "")
    try:
        if value.isascii() and value.isdecimal():
            return now + timedelta(seconds=int(value))
        parsed = parsedate_to_datetime(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except ValueError, TypeError, OverflowError:
        return None


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
    if trigger in {"schedule", "catchup"} and not slot_key:
        raise ValueError("Scheduled runs require a slot_key")
    run = CollectorRun(
        source_id=source_id,
        trigger=trigger,
        slot_key=slot_key,
        queued_at=datetime.now(UTC),
        status="queued",
    )
    session.add(run)
    session.flush()
    run_id = run.id  # Bound before commit: an expired reload would reopen a transaction.
    session.commit()
    try:
        publish(run_id)
    except Exception:
        session.execute(
            update(CollectorRun)
            .where(CollectorRun.id == run_id, CollectorRun.status == "queued")
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
    result: CollectorRunTarget,
    source: Source,
    adapter: Adapter[R],
    request: Request,
    settings: Settings,
    deadline: float,
    request_hook: RequestHook | None,
) -> tuple[Response, RawPayload]:
    if request.raw_payload_id is not None:
        if request.mode not in {"csv", "json", "fixture"}:
            raise ValueError("Existing raw captures require an offline request")
        if time.monotonic() >= deadline:
            raise RunDeferred("wall_time_budget")
        payload = session.get_one(RawPayload, request.raw_payload_id)
        if payload.source_id != run.source_id or payload.storage_key is None:
            raise ValueError("Existing raw capture must belong to the source and have a body")
        result.raw_payload_id = payload.id
        return Response(None, payload.status_code, payload.content_type, payload.etag), payload
    for attempt in range(settings.collector_max_retries + 1):
        while True:
            if time.monotonic() >= deadline:
                raise RunDeferred("wall_time_budget")
            session.refresh(source)
            if request.mode != "live":
                break
            if not source.enabled:
                raise RunDeferred("source_disabled")
            wait = (
                (source.retry_not_before - datetime.now(UTC)).total_seconds()
                if source.retry_not_before
                else 0
            )
            if wait <= 0:
                break
            session.commit()
            if wait > settings.collector_retry_wait_cap_seconds:
                raise RunDeferred("retry_not_before")
            if time.monotonic() + wait >= deadline:
                raise RunDeferred("wall_time_budget")
            time.sleep(wait)
        source_id, source_key, run_id = source.id, source.key, run.id
        if request.mode == "live":
            require_live(request, settings)  # A closed guard must not debit quota or count.
            if request_hook is not None:
                request_hook(session, source, run, request, None)
        run.http_requests += int(request.mode == "live")
        session.commit()
        retry_at = None
        try:
            response = fetch(adapter, request, settings=settings)
        except TimeoutError, ConnectionError:
            session.commit()
            if attempt == settings.collector_max_retries:
                raise
        else:
            captured_at = datetime.now(UTC)
            payload = storage.store_capture(
                session,
                source_id=source_id,
                source_key=source_key,
                run_id=run_id,
                body=response.body,
                content_type=response.content_type,
                status_code=response.status_code,
                etag=response.etag,
                request=request.params,
                captured_at=captured_at,
            )
            run.last_status_code = response.status_code
            result.raw_payload_id = payload.id  # Linked even if the after-hook fails.
            if request.mode == "live":
                # Block state from the current row: an owner may have disabled it mid-fetch.
                session.refresh(source, with_for_update=True)
                source.last_status_code = response.status_code
                if response.status_code in BLOCK_STATUSES:
                    source.consecutive_block_count += 1
                elif request.resets_blocks:
                    source.consecutive_block_count = 0
                if (
                    source.enabled
                    and source.consecutive_block_count >= settings.collector_block_threshold
                ):
                    source.enabled, source.status = False, "blocked"
                    source.disabled_at = captured_at
                    source.disabled_reason = f"consecutive_blocks:http_{response.status_code}"
                    session.add(
                        SourceEvent(
                            source_id=source_id,
                            actor="system",
                            action="disable",
                            reason=source.disabled_reason,
                            at=captured_at,
                        )
                    )
                if response.status_code in BLOCK_STATUSES | RETRY_STATUSES:
                    retry_at = _retry_after(response, captured_at)
                    if retry_at is not None:
                        source.retry_not_before = max(source.retry_not_before or retry_at, retry_at)
            session.commit()
            if request.mode == "live" and request_hook is not None:
                try:
                    request_hook(session, source, run, request, response)
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    if response.status_code in BLOCK_STATUSES:
                        raise RunDeferred(f"http_{response.status_code}") from exc
                    raise
            if (
                response.status_code not in RETRY_STATUSES
                or attempt == settings.collector_max_retries
            ):
                return response, payload
        delay = (
            0
            if retry_at is not None and retry_at > datetime.now(UTC)
            else min(
                settings.collector_backoff_base_seconds * 4**attempt,
                settings.collector_backoff_cap_seconds,
            )
        )
        if time.monotonic() + delay >= deadline:
            raise RunDeferred("wall_time_budget")
        if delay:
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
    request_hook: RequestHook | None = None,
    stop_exceptions: tuple[type[BaseException], ...] = (),
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
    # This dedicated session must not lazy-load expired payloads before the S3 GET.
    session.expire_on_commit = False
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
    caught_exceptions: tuple[type[BaseException], ...] = (Exception, *stop_exceptions)
    for target, result in zip(targets, evidence, strict=True):
        complete = True
        try:
            if stopped:
                raise RunDeferred("run_stopped")
            for request in target.requests:
                response, payload = _capture(
                    session, run, result, source, adapter, request, settings, deadline, request_hook
                )
                session.commit()
                if response.status_code in BLOCK_STATUSES:
                    raise RunDeferred(f"http_{response.status_code}")
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
        except caught_exceptions as exc:
            session.rollback()
            result.status = "partial" if result.raw_payload_id is not None else "failed"
            if not stopped:
                run.error_code = type(exc).__name__
                run.error_message = (
                    str(exc)
                    if isinstance(exc, (RunDeferred, ResponseFailed))
                    else type(exc).__name__
                )
            if isinstance(exc, (RunDeferred, CollectorsLiveDisabled, *stop_exceptions)):
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
