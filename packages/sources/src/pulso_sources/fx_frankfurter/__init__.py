"""Frankfurter blended FX; run through the framework's live/fixture boundary."""

import json
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime, time, timedelta
from datetime import date as Date
from decimal import Decimal
from http.client import HTTPException, HTTPSConnection
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import FxRate, RawPayload, SourceEvent
from pulso_core.money import CURRENCY_EXPONENTS
from pulso_core.settings import get_settings
from pulso_sources.framework import Request, Response, Target, UpsertStats

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData

QUOTES = tuple(code for code in CURRENCY_EXPONENTS if code != "USD")
SOURCE = "frankfurter_blended"


class Rate(BaseModel):
    date: Date
    base: str
    quote: str
    rate: Decimal = Field(gt=0, max_digits=18, decimal_places=8)

    @field_validator("base", "quote")
    @classmethod
    def currency(cls, value: str) -> str:
        if value not in CURRENCY_EXPONENTS:
            raise ValueError("Unsupported currency")
        return value


def plan(session: Session, day: Date) -> list[Target]:
    """Daily latest plus the missing range, starting in 2025 on the first run."""
    latest = {
        quote: last
        for quote, last in session.execute(
            select(FxRate.quote, func.max(FxRate.date))
            .where(FxRate.base == "USD", FxRate.source == SOURCE)
            .group_by(FxRate.quote)
        )
    }
    start = min(latest.get(quote, Date(2024, 12, 31)) for quote in QUOTES)
    if latest:  # A quote lagging the newest one by >31 days (or never returned) stops pinning it.
        start = max(start, max(latest.values()) - timedelta(days=31))
    start += timedelta(days=1)
    # One target: a failed backfill must prevent latest from advancing the date watermark.
    requests = list(backfill(start, day - timedelta(days=1))[0].requests) if start < day else []
    requests.append(Request(params={"base": "USD", "quotes": ",".join(QUOTES)}))
    return [Target("fx", "daily", requests)]


def backfill(start: Date, end: Date) -> list[Target]:
    if start > end:
        raise ValueError("FX backfill start must not follow end")
    return [
        Target(
            "fx",
            "backfill",
            [
                Request(
                    params={
                        "base": "USD",
                        "quotes": ",".join(QUOTES),
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                    }
                )
            ],
        )
    ]


def rate_as_of(session: Session, quote: str, day: Date, *, source: str = SOURCE) -> FxRate | None:
    """Carry forward the last observed rate known before the UTC day cutoff (D4)."""
    cutoff = datetime.combine(day + timedelta(days=1), time(), UTC)
    return session.scalar(
        select(FxRate)
        .where(
            FxRate.base == "USD",
            FxRate.quote == quote,
            FxRate.source == source,
            FxRate.date <= day,
            FxRate.captured_at < cutoff,
        )
        .order_by(FxRate.date.desc(), FxRate.captured_at.desc(), FxRate.raw_payload_id.desc())
        .limit(1)
    )


class FrankfurterAdapter:
    parser_version = "1"

    def __init__(self, data: ImportData | None = None) -> None:
        self.data = data

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        if set(request.params) - {"base", "quotes", "from", "to"}:
            raise ValueError("Only blended FX requests are supported")
        try:
            with closing(
                HTTPSConnection(
                    "api.frankfurter.dev", timeout=get_settings().collector_request_timeout_seconds
                )
            ) as connection:
                connection.request(
                    "GET",
                    "/v2/rates?" + urlencode(request.params),
                    headers={"User-Agent": user_agent, "Accept": "application/json"},
                )
                with closing(connection.getresponse()) as response:
                    return Response(
                        response.read(),
                        response.status,
                        response.getheader("Content-Type"),
                        response.getheader("ETag"),
                        headers=dict(response.getheaders()),
                    )
        except (OSError, HTTPException) as exc:
            raise ConnectionError("Frankfurter transport failed") from exc

    def parse(self, body: bytes) -> Sequence[Rate]:
        rows = (
            self.data.csv.rows
            if self.data is not None and self.data.csv is not None
            else json.loads(body, parse_float=Decimal)
        )
        if not isinstance(rows, list):
            raise ValueError("Expected a Frankfurter v2 rate array")
        records = [Rate.model_validate(row) for row in rows]
        keys = [(row.date, row.base, row.quote) for row in records]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate FX pair/date in capture")
        return records

    def upsert(
        self, session: Session, records: Sequence[Rate], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        if payload.captured_at.utcoffset() is None or not 1 <= len(parser_version) <= 80:
            raise ValueError("FX requires an aware capture time and parser version")
        if any(row.date > payload.captured_at.astimezone(UTC).date() for row in records):
            raise ValueError("FX date is later than capture date")
        source = "manual" if self.data is not None else SOURCE
        inserted, conflict = 0, False
        for row in records:
            key = {"date": row.date, "base": row.base, "quote": row.quote, "source": source}
            added = session.scalar(
                insert(FxRate)
                .values(
                    **key,
                    rate=row.rate,
                    observed_for=row.date,
                    captured_at=payload.captured_at,
                    raw_payload_id=payload.id,
                    parser_version=parser_version,
                )
                .on_conflict_do_nothing(index_elements=list(FxRate.observation_keys))
                .returning(FxRate.rate)
            )
            inserted += added is not None
            if added is None and session.scalar(select(FxRate.rate).filter_by(**key)) != row.rate:
                conflict = True
        reason = f"raw_payload_id={payload.id};parser_version={parser_version}"
        if (
            conflict
            and session.scalar(
                select(SourceEvent.id)
                .filter_by(source_id=payload.source_id, action="fx_conflict", reason=reason)
                .limit(1)
            )
            is None
        ):
            session.add(
                SourceEvent(
                    source_id=payload.source_id,
                    actor="system",
                    action="fx_conflict",
                    reason=reason,
                    at=payload.captured_at,
                )
            )
            session.flush()
        return UpsertStats(inserted=inserted, unchanged=len(records) - inserted)
