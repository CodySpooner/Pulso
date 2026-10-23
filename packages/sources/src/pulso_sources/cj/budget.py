"""Reserve quota before an attempt; the collector owns the commit before HTTP."""

from datetime import UTC, datetime

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
    source.config = {**source.config, "cj_points": {"day": day, "reserved": used + cost}}
    run.params = {
        **run.params,
        "cj_points_reserved": run.params.get("cj_points_reserved", 0) + cost,
    }
