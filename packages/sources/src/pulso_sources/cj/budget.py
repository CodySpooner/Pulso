"""Reserve quota before an attempt; the collector owns the commit before HTTP."""

import json
from datetime import UTC, datetime, timedelta
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, model_validator
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, Source
from pulso_core.settings import Settings
from pulso_sources.cj.errors import CJError

POINTS = {
    "/product/listV2": 50,
    "/product/query": 10,
    "/product/stock/getInventoryByPid": 10,
    "/logistic/freightCalculate": 10,
}


class PointsInfo(BaseModel):
    usedToday: Annotated[StrictInt, Field(ge=0)]
    remaining: Annotated[StrictInt, Field(ge=0)]
    total: Annotated[StrictInt, Field(ge=0)]

    @model_validator(mode="after")
    def within_total(self) -> PointsInfo:
        if self.remaining > self.total:
            raise ValueError("CJ remaining points exceed total")
        return self


def record_points(source: Source, body: bytes | None, now: datetime) -> None:
    """Keep only quota metadata, including from auth; never persist its token body.

    A body without pointsInfo keeps the debited evidence; a present invalid one clears it.
    """
    try:
        data = json.loads(body or b"{}")
    except ValueError:
        return
    if not isinstance(data, dict) or "pointsInfo" not in data:
        return
    state = None
    try:
        info = PointsInfo.model_validate(data["pointsInfo"])
        state = {
            "info": info.model_dump(),
            "captured_at": now.isoformat(),
            "at": now.isoformat(),
            "balance": info.remaining * 1440,
        }
    except ValueError:
        pass  # Present but invalid: unknown, so paid sends fail closed.
    source.config = {**source.config, "cj_provider_points": state}


def reserve(
    session: Session,
    source: Source,
    run: CollectorRun,
    endpoint: str,
    *,
    settings: Settings,
    now: datetime,
) -> None:
    if source.key != "cj" or run.source_id != source.id or now.utcoffset() is None:
        raise ValueError("CJ budget requires its source, run and aware UTC date")
    cost = POINTS[endpoint]
    # The scheduler holds the source lock; the row lock also serializes quota reservation.
    session.refresh(source, with_for_update=True)
    day = now.astimezone(UTC).date().isoformat()
    quota = source.config.get("cj_points", {})
    used = quota.get("reserved", 0) if quota.get("day") == day else 0
    if type(used) is not int or used < 0:
        raise ValueError("Invalid persisted CJ quota")
    if used + cost > settings.cj_daily_points_budget:
        raise CJError("cj_daily_budget", "CJ daily points budget reached")
    provider = source.config.get("cj_provider_points")
    if provider is None:
        raise CJError("cj_points_unknown", "CJ provider points are unknown")
    info = PointsInfo.model_validate(provider["info"])
    at = datetime.fromisoformat(provider["at"])
    if at.utcoffset() is None or at > now or at.astimezone(UTC).date().isoformat() != day:
        raise CJError("cj_points_unknown", "CJ provider points need current-day evidence")
    minutes = (now - at) // timedelta(minutes=1)
    # Integer 1/1440-point units preserve fractional refill without rounding up.
    balance = min(info.total * 1440, provider["balance"] + minutes * info.total)
    if balance < cost * 1440:
        raise CJError("cj_points_exhausted", "CJ provider points cannot cover the next request")
    source.config = {
        **source.config,
        "cj_points": {"day": day, "reserved": used + cost},
        "cj_provider_points": {
            **provider,
            "at": now.isoformat(),  # Discard partial minutes before a debit conservatively.
            "balance": balance - cost * 1440,
        },
    }
    run.params = {
        **run.params,
        "cj_points_reserved": run.params.get("cj_points_reserved", 0) + cost,
    }
