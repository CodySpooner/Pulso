"""Data Health admin API (DH-1). Never returns or logs source config beyond seed approval."""

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy import Date, Integer, String, column, func, select, table
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement
from starlette.responses import Response

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.schemas.admin import (
    CoverageDay,
    Gap,
    Heartbeat,
    HostHealth,
    ImportPreview,
    ImportResult,
    RowError,
    Run,
    RunDetail,
    RunPage,
    RunTarget,
    SourceHealth,
    SourcePatch,
)
from pulso_core.models import (
    CollectionGap,
    CollectorRun,
    CollectorRunTarget,
    HostHeartbeat,
    Source,
    SourceEvent,
)
from pulso_core.settings import Settings, get_settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.framework import enqueue_run
from pulso_sources.imports import ADAPTERS, TEMPLATES, commit_import, parse_csv, template_csv
from pulso_sources.imports.csv import MAX_BYTES, DuplicateEntityRows, ParsedCSV
from pulso_sources.seed_approval import SEED_SOURCES, approved_targets, is_approved_seed

logger = logging.getLogger("pulso.api")
router = APIRouter(prefix="/v1/admin", dependencies=[Depends(current_principal)])
MAX_ERRORS = 100  # first row errors returned; counts stay complete (P1-22 finding 4)
DB = Annotated[Session, Depends(get_db)]
UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/octet-stream": {
                "schema": {
                    "type": "string",
                    "contentMediaType": "application/octet-stream",
                    "title": "Body",
                    "description": "The file's raw bytes.",
                }
            }
        },
    }
}
COVERAGE = table(
    "source_daily_coverage",
    column("source_id", Integer),
    column("day", Date),
    column("status", String),
    *(column(name, Integer) for name in ("runs", "rows", "targets", "successful_targets")),
)


def get_publisher() -> Callable[[int], object]:
    """P1-04 overrides this with the Celery publish; until then manual runs stay queued."""
    return lambda run_id: None


def live_runs_allowed(settings: Settings) -> bool:
    return settings.collectors_live and not is_linked_worktree(__file__)


def runs(session: Session, *where: ColumnElement[bool], limit: int | None = None) -> list[Run]:
    def count(*extra: ColumnElement[bool]) -> ColumnElement[int]:
        return (
            select(func.count())
            .where(CollectorRunTarget.run_id == CollectorRun.id, *extra)
            .scalar_subquery()
        )

    rows = session.execute(
        select(
            # params can hold an import's row errors (megabytes); no response returns it.
            *(c for c in CollectorRun.__table__.c if c.key != "params"),
            Source.key.label("source_key"),
            count().label("target_count"),
            count(CollectorRunTarget.status == "success").label("successful_target_count"),
        )
        .join(Source, Source.id == CollectorRun.source_id)
        .where(*where)
        .order_by(CollectorRun.id.desc())
        .limit(limit)
    )
    return [Run.model_validate(dict(row._mapping)) for row in rows]


def get_source(session: Session, key: str) -> Source:
    source = session.scalar(select(Source).where(Source.key == key))
    if source is None:
        raise APIError(404, "not_found", "Source not found.")
    return source


def csv_import(key: str) -> Literal["ready", "preview_only"] | None:
    if key not in TEMPLATES:
        return None
    return "ready" if key in ADAPTERS else "preview_only"


def source_health(session: Session) -> list[SourceHealth]:
    latest = select(func.max(CollectorRun.id)).group_by(CollectorRun.source_id)
    last_runs = {run.source_key: run for run in runs(session, CollectorRun.id.in_(latest))}
    # ponytail: aggregates all success targets; add a source/day bound once volume needs it.
    freshness = dict(
        session.execute(
            select(CollectorRun.source_id, func.max(CollectorRunTarget.captured_at))
            .join(CollectorRunTarget, CollectorRunTarget.run_id == CollectorRun.id)
            .where(CollectorRunTarget.status == "success")
            .group_by(CollectorRun.source_id)
        )
        .tuples()
        .all()
    )
    result = []
    for source in session.scalars(select(Source).order_by(Source.id)):
        seeded = source.key in SEED_SOURCES.values()
        seed = source.config.get("seed")
        result.append(
            SourceHealth(
                key=source.key,
                name=source.name,
                type=source.type,
                phase=source.phase,
                enabled=source.enabled,
                status=source.status,
                disabled_reason=source.disabled_reason,
                disabled_at=source.disabled_at,
                retry_not_before=source.retry_not_before,
                last_status_code=source.last_status_code,
                last_run=last_runs.get(source.key),
                freshness=freshness.get(source.id),
                seed_approved=isinstance(seed, dict) and is_approved_seed(seed) if seeded else None,
                approved_targets=len(approved_targets(session, source.key)) if seeded else None,
                csv_import=csv_import(source.key),
            )
        )
    return result


@router.get("/sources", response_model=list[SourceHealth])
def list_sources(session: DB) -> list[SourceHealth]:
    return source_health(session)


@router.patch("/sources/{key}", response_model=SourceHealth)
def patch_source(
    key: str,
    patch: SourcePatch,
    session: DB,
    principal: Annotated[Principal, Depends(current_principal)],
) -> SourceHealth:
    source = get_source(session, key)
    # Lock until commit and re-read, so a framework block committed meanwhile decides (R1).
    session.refresh(source, with_for_update=True)
    reason = (patch.reason or "").strip() or None
    now = datetime.now(UTC)
    if patch.enabled:
        if source.status == "blocked" and reason is None:  # §4.2: typed reason to re-enable
            raise APIError(422, "reason_required", "Re-enabling a blocked source needs a reason.")
        source.status, source.disabled_reason, source.disabled_at = "active", None, None
    elif source.status != "blocked":  # keep the block so re-enabling still needs a reason
        source.status, source.disabled_reason, source.disabled_at = "disabled", reason, now
    source.enabled = patch.enabled
    action = "enable" if patch.enabled else "disable"
    session.add(
        SourceEvent(
            source_id=source.id, actor=str(principal.user_id), action=action, reason=reason, at=now
        )
    )
    session.commit()
    return next(health for health in source_health(session) if health.key == key)


@router.post("/sources/{key}/run", response_model=Run, status_code=202)
def run_source(
    key: str,
    session: DB,
    settings: Annotated[Settings, Depends(get_settings)],
    publish: Annotated[Callable[[int], object], Depends(get_publisher)],
) -> Run:
    source = get_source(session, key)
    if not live_runs_allowed(settings):
        raise APIError(
            409, "collectors_live_off", "Live collectors run only on the collector host."
        )
    if not source.enabled:
        raise APIError(409, "source_disabled", "Enable the source before running it.")

    def publish_run(run_id: int) -> object:
        try:
            return publish(run_id)
        except Exception as exc:
            # Broker errors can embed connection strings: log the class only (I1).
            # enqueue_run records publish_failed, then re-raises this fixed-text error.
            logger.error("run_publish_failed", extra={"error_type": type(exc).__name__})
            raise APIError(500, "internal_error", "An internal error occurred.") from None

    run = enqueue_run(session, source_id=source.id, trigger="manual", publish=publish_run)
    return runs(session, CollectorRun.id == run.id)[0]


@router.get("/runs", response_model=RunPage)
def list_runs(
    session: DB,
    source: str | None = None,
    cursor: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RunPage:
    where = [Source.key == source] if source else []
    if cursor:
        where.append(CollectorRun.id < cursor)
    items = runs(session, *where, limit=limit + 1)
    more = len(items) > limit
    return RunPage(items=items[:limit], next_cursor=items[limit - 1].id if more else None)


@router.get("/runs/{run_id}", response_model=RunDetail)
def get_run(run_id: int, session: DB) -> RunDetail:
    found = runs(session, CollectorRun.id == run_id)
    if not found:
        raise APIError(404, "not_found", "Run not found.")
    # ponytail: unpaginated; Phase 1 seed lists keep targets per run in the tens.
    targets = session.scalars(
        select(CollectorRunTarget)
        .where(CollectorRunTarget.run_id == run_id)
        .order_by(CollectorRunTarget.scope, CollectorRunTarget.target_id)
    )
    return RunDetail(
        **found[0].model_dump(), targets=[RunTarget.model_validate(t) for t in targets]
    )


@router.get("/coverage", response_model=list[CoverageDay])
def get_coverage(session: DB, days: Annotated[int, Query(ge=1, le=366)] = 90) -> list[CoverageDay]:
    start = datetime.now(UTC).date() - timedelta(days=days - 1)
    rows = session.execute(
        select(Source.key.label("source_key"), *(c for c in COVERAGE.c if c.key != "source_id"))
        .join(Source, Source.id == COVERAGE.c.source_id)
        # The backup pseudo-source has its own card (DEC-060).
        .where(COVERAGE.c.day >= start, Source.type != "internal")
        .order_by(Source.key, COVERAGE.c.day)
    )
    return [CoverageDay.model_validate(dict(row._mapping)) for row in rows]


@router.get("/host", response_model=HostHealth)
def get_host(session: DB, settings: Annotated[Settings, Depends(get_settings)]) -> HostHealth:
    heartbeat = session.scalar(select(HostHeartbeat).order_by(HostHeartbeat.at.desc()).limit(1))
    gaps = session.execute(
        select(CollectionGap.__table__, Source.key.label("source_key"))
        .join(Source, Source.id == CollectionGap.source_id)
        .where(
            CollectionGap.filled_by_run_id.is_(None),
            CollectionGap.slot_start >= datetime.now(UTC) - timedelta(days=90),
        )
        .order_by(CollectionGap.slot_start.desc())
    )
    return HostHealth(
        live_runs_allowed=live_runs_allowed(settings),
        latest_heartbeat=Heartbeat.model_validate(heartbeat) if heartbeat else None,
        open_gaps=[Gap.model_validate(dict(row._mapping)) for row in gaps],
    )


def import_source(session: Session, key: str) -> Source:
    source = get_source(session, key)
    if key not in TEMPLATES:
        raise APIError(404, "not_found", "This source has no import template.")
    return source


async def read_upload(request: Request) -> bytes:
    # A Body(bytes) parameter would buffer the entire upload before this dependency runs.
    try:
        declared = int(request.headers.get("content-length", ""))
    except ValueError:
        declared = 0
    if declared > MAX_BYTES:
        raise APIError(422, "invalid_file", "File exceeds 20 MiB")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BYTES:
            raise APIError(422, "invalid_file", "File exceeds 20 MiB")
        body.extend(chunk)
    if not body:
        raise RequestValidationError(
            [{"loc": ("body",), "msg": "Field required", "type": "missing"}]
        )
    return bytes(body)


Upload = Annotated[bytes, Depends(read_upload)]


@router.get(
    "/sources/{key}/import/template",
    response_class=Response,
    responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}},
)
def get_import_template(key: str, session: DB) -> Response:
    import_source(session, key)
    return Response(
        template_csv(key),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{key}-template.csv"'},
    )


@router.post(
    "/sources/{key}/import/preview", response_model=ImportPreview, openapi_extra=UPLOAD_BODY
)
def preview_import(key: str, body: Upload, session: DB) -> ImportPreview:
    source = import_source(session, key)
    # ponytail: validation-only until P1-07–09 register read-only classifiers for preview_csv.
    try:
        parsed = parse_csv(key, body, mapping=source.config.get("csv_mapping"))
    except DuplicateEntityRows as exc:  # the whole file is rejected; the errors name the rows
        parsed = ParsedCSV([], exc.errors, 0)
    except ValueError as exc:
        utf8 = isinstance(exc, UnicodeDecodeError)
        raise APIError(
            422, "invalid_file", "Save the file as CSV UTF-8." if utf8 else str(exc)
        ) from exc
    return ImportPreview(
        rows=parsed.rows[:20],
        valid=len(parsed.rows),
        invalid=len({error.row for error in parsed.errors}),
        skipped=parsed.skipped,
        error_count=len(parsed.errors),
        errors=[RowError.model_validate(error) for error in parsed.errors[:MAX_ERRORS]],
    )


@router.post("/sources/{key}/import", response_model=ImportResult, openapi_extra=UPLOAD_BODY)
def commit_source_import(
    key: str,
    body: Upload,
    session: DB,
    settings: Annotated[Settings, Depends(get_settings)],
    mode: Literal["csv", "json"] = "csv",
    observed_for: date | None = None,
) -> ImportResult:
    import_source(session, key)
    if mode == "json" and (key != "shopify_stores" or observed_for is None):
        raise APIError(
            422, "invalid_import", "JSON imports are Shopify-only and need observed_for."
        )
    if key not in ADAPTERS:  # otherwise commit_import would record a KeyError run
        raise APIError(
            409, "import_unavailable", "This source has no import adapter yet; preview works."
        )
    run = commit_import(session, key, body, settings=settings, mode=mode, observed_for=observed_for)
    params = run.params or {}
    return ImportResult(
        run=runs(session, CollectorRun.id == run.id)[0],
        raw_payload_id=params.get("raw_payload_id"),
        original_run_id=params.get("original_run_id"),
        in_progress=params.get("reason") == "in_progress",
        error_count=params.get("error_count", 0),
        errors=params.get("errors", [])[:MAX_ERRORS],
    )
