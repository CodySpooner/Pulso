"""Trends capture parsing, the weekly keyword set and conservative monthly/hourly reservations."""

import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import TYPE_CHECKING, Literal, NamedTuple
from uuid import UUID

from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Product,
    ProductKeyword,
    RawPayload,
    SearchTrend,
    Source,
)
from pulso_core.settings import Settings, get_settings
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
ACCOUNT_ERRORS = {"serpapi_invalid_key", "serpapi_searches_exhausted"}


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


def reserve_hourly(source: Source, limit: int, at: datetime) -> None:
    """Rolling 60 minutes beside `reserve`, same lock and commit; no refunds, no waiting (DEC-154).

    An attempt exactly 60 minutes old still counts, so no closed hour exceeds the limit.
    """
    if not 1 <= limit <= 50:
        raise ValueError("Invalid Trends hourly limit")
    recent = [
        stamp
        for stamp in source.config.get("trends_hourly", [])
        if at - datetime.fromisoformat(stamp) <= timedelta(hours=1)
    ]
    if len(recent) >= limit:
        raise TrendsError("trends_hourly_budget_exhausted")
    source.config = {**source.config, "trends_hourly": [*recent, at.isoformat()]}


class WeeklySet(NamedTuple):
    """One Monday run's keywords and the budget they sit in (KW-2, DEC-292)."""

    keywords: list[str]  # plan order: the approved seeds, then confirmed product keywords
    cap: int  # keywords a week: monthly_limit // 5, since a month has at most five Mondays
    monthly_limit: int  # TRENDS_MONTHLY_SEARCH_LIMIT; `reserve` still enforces it per attempt
    confirmed: bool  # TRENDS_CONFIRMED_KEYWORDS: off, only the seeds, as before KW-2


def normal(keyword: str) -> str:
    """Two keywords are one search when they match casefolded with spacing collapsed."""
    return " ".join(keyword.casefold().split())


def confirmed_keywords(session: Session) -> list[str]:
    """Every workspace's confirmed keywords: the most workspaces first, then the earliest
    confirmation, then A to Z. A workspace's newest decision on a product or one merged into it
    counts, as the Trends tab reads them (DEC-263, DEC-281), so a later rejection wins."""
    merged = dict(
        session.execute(
            select(Product.id, Product.merged_into_id).where(Product.merged_into_id.is_not(None))
        )
        .tuples()
        .all()
    )

    def live(product_id: UUID) -> UUID:
        while (into := merged.get(product_id)) is not None:
            product_id = into
        return product_id

    # ponytail: every decision in one read; fine at v1's hundreds, aggregate in SQL past that.
    # Variants differ here by spelling only: the tab's plural folding (`lamps` is `lamp`) stays
    # in the API, so plural twins decided apart on two products before a merge both count.
    newest: dict[tuple[UUID, UUID, str], ProductKeyword] = {}
    for row in session.scalars(select(ProductKeyword).order_by(ProductKeyword.decided_at)):
        newest[row.workspace_id, live(row.product_id), normal(row.keyword)] = row
    workspaces: defaultdict[str, set[UUID]] = defaultdict(set)
    first: dict[str, datetime] = {}
    for (workspace, _, keyword), row in newest.items():
        if row.status == "confirmed":
            workspaces[keyword].add(workspace)
            first[keyword] = min(first.get(keyword, row.decided_at), row.decided_at)
    return sorted(workspaces, key=lambda k: (-len(workspaces[k]), first[k], k))


def weekly_set(session: Session, settings: Settings) -> WeeklySet:
    """The approved seeds, then (setting on) the confirmed keywords not already in the set, cut
    at the weekly cap. One past the cap, or holding a comma, is left out this week: never queued,
    never retried. The Trends tab counts with this function, so it never disagrees with `plan`."""
    seeds = [row["keyword"] for row in approved_targets(session, "google_trends")]
    if any("," in keyword for keyword in seeds):
        raise ValueError("Trends requires one keyword per search")
    limit = settings.trends_monthly_search_limit
    week = WeeklySet(seeds, limit // 5, limit, settings.trends_confirmed_keywords)
    if not week.confirmed:
        return week
    chosen: dict[str, str] = {}
    for keyword in [*seeds, *confirmed_keywords(session)]:
        if "," not in keyword:
            chosen.setdefault(normal(keyword), keyword)  # a seed keeps its spelling and place
    return week._replace(keywords=list(chosen.values())[: week.cap])


def plan(session: Session) -> list[Target]:
    return [
        Target("trends", keyword, [Request(params={**PARAMS, "q": keyword})])
        for keyword in weekly_set(session, get_settings()).keywords
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
    at = datetime.now(UTC)
    reserve(source, settings.trends_monthly_search_limit, at)
    # A full hour stops the run; the framework's rollback also drops the monthly +1 above.
    reserve_hourly(source, settings.trends_hourly_search_limit, at)


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
            if code in ACCOUNT_ERRORS:
                raise TrendsError(code)
            raise ValueError(code)
        data = json.loads(body)
        params = data["search_parameters"]
        if (
            any(str(params.get(k)) != str(v) for k, v in PARAMS.items())
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
