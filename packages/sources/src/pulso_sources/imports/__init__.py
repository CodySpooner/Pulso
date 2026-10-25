"""Offline imports. Functions that commit/replay own a dedicated Session's transactions."""

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.amazon import ImportAdapter as AmazonImportAdapter
from pulso_sources.cj.csv import ImportAdapter as CJImportAdapter
from pulso_sources.framework import Adapter, Request, Target, enqueue_run, execute_run
from pulso_sources.fx_frankfurter import FrankfurterAdapter
from pulso_sources.google_trends.live import GoogleTrendsAdapter
from pulso_sources.imports.csv import (
    DuplicateEntityRows,
    ParsedCSV,
    Preview,
    Row,
    RowError,
    parse_csv,
    preview_csv,
)
from pulso_sources.imports.csv import decode_upload as _decode_upload
from pulso_sources.imports.templates import TEMPLATES, template_csv
from pulso_sources.merchant_bestsellers import ImportAdapter as MerchantImportAdapter
from pulso_sources.shopify_stores.imports import Context, ShopifyImportAdapter


@dataclass(frozen=True)
class ImportData:
    """Factories consume validated CSV rows in parse(); JSON parse() receives original bytes.

    Adapters own row-to-observation mapping: use date/observed_for from each CSV row,
    falling back to payload.captured_at.date(); JSON uses this context's observed_for.
    Always copy payload.id/captured_at and the runner's parser_version into observations.
    Group CSV variants by listing and aggregate their prices before writing its snapshot.
    """

    mode: Literal["csv", "json"]
    csv: ParsedCSV | None
    observed_for: date | None


# Source modules register factories at startup, e.g. ADAPTERS["cj"] = make_import_adapter.
ADAPTERS: dict[str, Callable[[ImportData], Adapter[Any]]] = {
    "shopify_stores": ShopifyImportAdapter,
    "fx_frankfurter": FrankfurterAdapter,
    "google_trends": GoogleTrendsAdapter,
    "cj": CJImportAdapter,
    "merchant_bestsellers": MerchantImportAdapter,
    "amazon": AmazonImportAdapter,
}


def _prepare(
    source_key: str,
    body: bytes,
    mode: Literal["csv", "json"],
    mapping: Mapping[str, str] | None,
    observed_for: date | None,
    as_of: date,
) -> ImportData:
    if mode == "csv":
        return ImportData(mode, parse_csv(source_key, body, mapping=mapping, as_of=as_of), None)
    if mode != "json" or source_key != "shopify_stores" or type(observed_for) is not date:
        raise ValueError("Shopify JSON requires the owner's observed_for date")
    if observed_for > as_of:
        raise ValueError("observed_for is later than the UTC capture date")

    def invalid_constant(value: str) -> None:
        raise ValueError("JSON must not contain non-finite numbers")

    json.loads(_decode_upload(body), parse_constant=invalid_constant)
    return ImportData(mode, None, observed_for)


def _error_params(errors: Sequence[RowError]) -> dict[str, Any]:
    return {
        "errors": [asdict(error) for error in errors[:100]],
        "error_count": len(errors),
        "invalid_rows": len({error.row for error in errors}),
        "errors_by_column": dict(Counter(error.column for error in errors)),
    }


def _execute(
    session: Session,
    run: CollectorRun,
    payload: RawPayload,
    data: ImportData,
    adapter: Adapter[Any],
    settings: Settings,
) -> CollectorRun:
    run.params = {
        "raw_payload_id": payload.id,
        "parser_version": adapter.parser_version,
        **_error_params(data.csv.errors if data.csv else []),
        "skipped": data.csv.skipped if data.csv else 0,
    }
    if data.csv is not None and not data.csv.rows:
        run.status, run.finished_at = "failed", datetime.now(UTC)
        run.error_code = run.error_message = "no_valid_rows"
        session.commit()
        return run
    session.commit()
    return execute_run(
        session,
        run.id,
        adapter,
        [Target("import", str(payload.id), [Request(mode=data.mode, raw_payload_id=payload.id)])],
        settings=settings,
    )


def _from_capture(payload: RawPayload, source_key: str) -> tuple[ImportData, Adapter[Any]]:
    """Rebuild an import from the capture's own bytes, capture date and request metadata."""
    if payload.template_version not in {TEMPLATES[source_key].template_version, "shopify-json-v1"}:
        raise ValueError("Capture is not a supported import")
    metadata = payload.request
    observed_for = (
        date.fromisoformat(metadata["observed_for"]) if metadata.get("observed_for") else None
    )
    data = _prepare(
        source_key,
        storage.read_capture(payload),
        metadata["mode"],
        metadata.get("mapping"),
        observed_for,
        payload.captured_at.date(),
    )
    return data, ADAPTERS[source_key](data)


def _failed(session: Session, run: CollectorRun, exc: Exception) -> CollectorRun:
    session.rollback()
    if isinstance(exc, DuplicateEntityRows):
        run.params = _error_params(exc.errors)
    run.status, run.finished_at = "failed", datetime.now(UTC)
    run.error_code = run.error_message = type(exc).__name__
    session.commit()
    return run


def _active_run(session: Session, payload: RawPayload, settings: Settings) -> int | None:
    """Under the caller's source lock, first end stale import claims as abandoned (DEC-221)."""
    claims = (
        CollectorRun.status.in_(["queued", "running"]),
        or_(
            CollectorRun.id == payload.run_id,
            CollectorRun.params["raw_payload_id"].as_integer() == payload.id,
        ),
    )
    # DEC-098's max(2 h, twice the budget); imports run on execute_run's default budget.
    stale = max(timedelta(hours=2), timedelta(seconds=2 * settings.collector_wall_time_seconds))
    now = datetime.now(UTC)
    session.execute(
        update(CollectorRun)
        .where(
            *claims,
            CollectorRun.trigger == "csv",
            func.coalesce(CollectorRun.started_at, CollectorRun.queued_at) <= now - stale,
        )
        .values(
            status="failed",
            complete=False,
            finished_at=now,
            error_code="abandoned",
            error_message="abandoned",
        )
    )
    return session.scalar(select(CollectorRun.id).where(*claims).limit(1))


def commit_import(
    session: Session,
    source_key: str,
    body: bytes,
    *,
    settings: Settings,
    mode: Literal["csv", "json"] = "csv",
    mapping: Mapping[str, str] | None = None,
    observed_for: date | None = None,
) -> CollectorRun:
    """Synchronous worker entry point; repeats of an imported capture skip before parsing,
    adapter lookup or S3. A capture with no successful run re-runs on its stored bytes and
    metadata with the current parser, unless a run on it is still queued/running (DEC-092)
    and younger than the stale threshold (DEC-221).

    Pass mapping from the preview; otherwise use sources.config.csv_mapping. Returns
    terminal run evidence (including sanitized failures), with row errors in params.
    """
    # As in execute_run, keep capture reads from reopening a transaction before S3.
    session.expire_on_commit = False
    source = session.scalars(select(Source).where(Source.key == source_key)).one()
    run = enqueue_run(session, source_id=source.id, trigger="csv", publish=lambda _: None)
    try:
        version = TEMPLATES[source_key].template_version if mode == "csv" else "shopify-json-v1"
        if mode not in {"csv", "json"} or (mode == "json" and source_key != "shopify_stores"):
            raise ValueError("Unsupported import mode/source")
        if mode == "csv" and observed_for is not None:
            raise ValueError("CSV rows carry their own dates; observed_for is JSON-only")
        # Serialize identity checks through capture commit, including concurrent uploads.
        session.execute(select(Source.id).where(Source.id == source.id).with_for_update())
        payload = session.scalar(
            select(RawPayload).where(
                RawPayload.source_id == source.id,
                RawPayload.sha256 == hashlib.sha256(body).hexdigest(),
                RawPayload.template_version == version,
            )
        )
        if payload is not None:
            done = session.scalar(
                select(CollectorRunTarget.run_id)
                .where(
                    CollectorRunTarget.raw_payload_id == payload.id,
                    CollectorRunTarget.status == "success",
                )
                .order_by(CollectorRunTarget.run_id)
                .limit(1)
            )
            active = _active_run(session, payload, settings)
            if done or active:
                run.status, run.finished_at = "skipped", datetime.now(UTC)
                reason = {} if done else {"reason": "in_progress"}
                run.params = {
                    "raw_payload_id": payload.id,
                    "original_run_id": done or active,
                    **reason,
                }
                session.commit()
                return run
            run.params = {"raw_payload_id": payload.id}
            session.commit()  # The params link claims the retry before the source lock drops.
            data, adapter = _from_capture(payload, source_key)
            return _execute(session, run, payload, data, adapter, settings)
        mapping = mapping if mapping is not None else source.config.get("csv_mapping", {})
        captured_at = datetime.now(UTC)
        data = _prepare(source_key, body, mode, mapping, observed_for, captured_at.date())
        adapter = ADAPTERS[source_key](data)
        payload = storage.store_capture(
            session,
            source_id=source.id,
            source_key=source_key,
            run_id=run.id,
            body=body,
            content_type="text/csv" if mode == "csv" else "application/json",
            status_code=None,
            etag=None,
            captured_at=captured_at,
            request={
                "mode": mode,
                "mapping": dict(mapping or {}),
                "observed_for": observed_for.isoformat() if observed_for else None,
                "parser_version": adapter.parser_version,
                "import_source": source_key,
                "shopify_import": Context.model_validate(
                    source.config.get("shopify_import")
                ).model_dump()
                if source_key == "shopify_stores"
                else None,
            },
        )
        payload.template_version = version
        session.commit()
        return _execute(session, run, payload, data, adapter, settings)
    except Exception as exc:
        return _failed(session, run, exc)


def replay_import(session: Session, raw_payload_id: int, *, settings: Settings) -> CollectorRun:
    """Explicit parser correction; preserve the original bytes, capture time and mapping."""
    session.expire_on_commit = False
    payload = session.get_one(RawPayload, raw_payload_id)
    source = session.get_one(Source, payload.source_id)
    run = enqueue_run(session, source_id=source.id, trigger="csv", publish=lambda _: None)
    try:
        session.execute(select(Source.id).where(Source.id == source.id).with_for_update())
        active = _active_run(session, payload, settings)
        run.params = {"raw_payload_id": payload.id}
        if active:
            run.status, run.finished_at = "skipped", datetime.now(UTC)
            run.params = {**run.params, "original_run_id": active, "reason": "in_progress"}
            session.commit()
            return run
        session.commit()  # Claim the replay before preparation, just like an upload retry.
        data, adapter = _from_capture(payload, source.key)
        if adapter.parser_version == payload.request["parser_version"]:
            raise ValueError("Parser correction requires a new parser_version")
        return _execute(session, run, payload, data, adapter, settings)
    except Exception as exc:
        return _failed(session, run, exc)


__all__ = [
    "ADAPTERS",
    "ImportData",
    "ParsedCSV",
    "Preview",
    "Row",
    "TEMPLATES",
    "commit_import",
    "parse_csv",
    "preview_csv",
    "replay_import",
    "template_csv",
]
