"""Trends capture parsing, approved targets and conservative monthly reservations."""

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, SearchTrend, Source
from pulso_core.settings import get_settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    RunDeferred,
    Target,
    UpsertStats,
    append_observation,
)
from pulso_sources.seed_approval import approved_targets
from pulso_sources.storage import JsonValue

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData

PARAMS: dict[str, JsonValue] = {
    "engine": "google_trends",
    "geo": "US",
    "tz": 0,
    "data_type": "TIMESERIES",
    "date": "today 3-m",
}


class TrendsError(RunDeferred):
    pass


class Point(BaseModel):
    keyword: str = Field(min_length=1)
    observed_for: date
    value: int = Field(strict=True, ge=0, le=100)
    geo: Literal["US"] = "US"
    window: Literal["today 3-m", "manual"] = "today 3-m"
    granularity: Literal["day"] = "day"
    metric: Literal["relative_interest"] = "relative_interest"
    is_partial: StrictBool = False


def error_code(body: bytes, status: int | None = None) -> str | None:
    try:
        data = json.loads(body)
        message = str(data.get("error", "")).lower() if isinstance(data, dict) else ""
    except ValueError:
        message = ""
    if status == 401 or ("api key" in message and "invalid" in message):
        return "serpapi_invalid_key"
    if "run out of searches" in message or "searches exhausted" in message:
        return "serpapi_searches_exhausted"
    if status in {403, 429}:
        return "serpapi_forbidden" if status == 403 else "serpapi_rate_limited"
    return "serpapi_error" if message else None


def reserve(source: Source, limit: int, at: datetime) -> None:
    """Caller holds the source row lock and commits before HTTP; no refunds."""
    if at.utcoffset() is None:
        raise ValueError("Quota time must be aware")
    month = at.astimezone(UTC).strftime("%Y-%m")
    quota = source.config.get("trends_quota", {})
    used = quota.get("used", 0) if quota.get("month") == month else 0
    if not 0 <= limit <= 250 or type(used) is not int or used < 0:
        raise ValueError("Invalid Trends quota")
    if used >= limit:
        raise TrendsError("trends_monthly_budget_exhausted")
    source.config = {**source.config, "trends_quota": {"month": month, "used": used + 1}}


def plan(session: Session) -> list[Target]:
    entries = approved_targets(session, "google_trends")
    if any("," in row["keyword"] for row in entries):
        raise ValueError("Trends requires one keyword per search")
    return [
        Target("trends", row["keyword"], [Request(params={**PARAMS, "q": row["keyword"]})])
        for row in entries
    ]


def series_as_of(session: Session, keyword: str, day: date) -> list[SearchTrend]:
    """One successful US daily capture known before the UTC cutoff, even when empty."""
    capture = session.scalar(
        select(RawPayload.id)
        .join(Source, Source.id == RawPayload.source_id)
        .join(CollectorRunTarget, CollectorRunTarget.raw_payload_id == RawPayload.id)
        .where(
            Source.key == "google_trends",
            CollectorRunTarget.scope == "trends",
            CollectorRunTarget.target_id == keyword,
            CollectorRunTarget.status == "success",
            RawPayload.captured_at < datetime.combine(day + timedelta(days=1), time(), UTC),
        )
        .order_by(RawPayload.captured_at.desc(), RawPayload.id.desc())
        .limit(1)
    )
    return list(
        session.scalars(
            select(SearchTrend)
            .where(SearchTrend.raw_payload_id == capture, SearchTrend.keyword == keyword)
            .order_by(SearchTrend.observed_for)
        )
    )


def request_hook(
    session: Session, source: Source, run: CollectorRun, request: Request, response: Response | None
) -> None:
    if request.mode != "live" or response is not None:
        return
    settings = get_settings()
    if not settings.collectors_live or is_linked_worktree(__file__):
        raise CollectorsLiveDisabled("Live collection requires the collector host")
    if not settings.serpapi_api_key:
        raise TrendsError("serpapi_missing_key")
    session.refresh(source, with_for_update=True)
    reserve(source, settings.trends_monthly_search_limit, datetime.now(UTC))


class GoogleTrendsParser:
    parser_version = "trends-1"

    def __init__(self, data: ImportData | None = None) -> None:
        self.data = data

    def parse(self, body: bytes) -> Sequence[Point]:
        if self.data is not None and self.data.csv is not None:
            return [
                Point.model_validate(
                    dict(
                        keyword=row["keyword"],
                        geo=row["geo"],
                        observed_for=row["date"],
                        value=row["interest"],
                        window="manual",
                    )
                )
                for row in self.data.csv.rows
            ]
        if code := error_code(body):
            raise TrendsError(code)
        data = json.loads(body)
        params = data["search_parameters"]
        if (
            any(params.get(k) != v for k, v in PARAMS.items())
            or not isinstance(params["q"], str)
            or not params["q"].strip()
            or "," in params["q"]
        ):
            raise ValueError("Unexpected Trends series parameters")
        records = []
        for point in data["interest_over_time"]["timeline_data"]:
            values = point["values"]
            if len(values) != 1 or values[0]["query"] != params["q"]:
                raise ValueError("Expected the requested keyword only")
            records.append(
                Point(
                    keyword=params["q"],
                    observed_for=datetime.fromtimestamp(int(point["timestamp"]), UTC).date(),
                    value=values[0]["extracted_value"],
                    is_partial=point.get("is_partial", False),
                )
            )
        if len({row.observed_for for row in records}) != len(records):
            raise ValueError("Duplicate date in Trends capture")
        return records

    def upsert(
        self,
        session: Session,
        records: Sequence[Point],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        if payload.captured_at.utcoffset() is None or any(
            row.observed_for > payload.captured_at.astimezone(UTC).date() for row in records
        ):
            raise ValueError("Observation is later than capture date")
        inserted = sum(
            append_observation(
                session,
                SearchTrend(
                    **row.model_dump(),
                    source_id=payload.source_id,
                    raw_payload_id=payload.id,
                    captured_at=payload.captured_at,
                    parser_version=parser_version,
                ),
            )
            for row in records
        )
        return UpsertStats(inserted=inserted, unchanged=len(records) - inserted)
