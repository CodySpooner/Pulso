"""Product time series (UX-5): the Trends tab's panes, global market data like the header."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Row, select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.admin import COVERAGE
from pulso_api.routers.products import DB, FAMILIES, NO_PRICE, is_stale
from pulso_api.schemas.provenance import NoSource
from pulso_core.models import Listing, ListingSnapshot, Product, ProductDailyFeature, Source

router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
Metric = Literal["price", "store_count", "search", "velocity_js", "velocity_bumps", "ads"]
Range = Literal["7d", "30d", "90d", "all"]
METRICS: tuple[Metric, ...] = get_args(Metric)
DAYS = {"7d": 7, "30d": 30, "90d": 90}
VELOCITY = {"velocity_js": "shp_inv", "velocity_bumps": "shp_bump"}  # metric → demand family
OBSERVED = ("success", "partial")  # source_daily_coverage: the source collected that UTC day
MISSING = {
    "search": "No search keyword is linked to this product yet. Keywords arrive in Phase 3.",
    "ads": "No ad source yet. Ad counts arrive in Phase 8 or by CSV import.",
}


class Point(BaseModel):
    day: date  # a UTC calendar day
    value: int  # price: the lowest USD minor price that day
    high: int | None  # price only: the highest
    as_of: AwareDatetime  # the newest capture the value uses: at or before day + 1 00:00Z


class SeriesGap(BaseModel):
    day: date
    status: Literal["gap", "failed"]  # source_daily_coverage: a missed slot, or every run failed


class Series(BaseModel):
    metric: Metric
    unit: Literal["usd_minor", "stores", "units_7d"]
    source: str
    source_name: str
    method: str | None  # set only on Pulso's own estimates (velocity)
    as_of: AwareDatetime  # the newest capture the series uses
    stale: bool
    points: list[Point]  # oldest first, one per observed day: an unobserved day has none
    gaps: list[SeriesGap]  # days the source recorded a gap or failure and the series has no point


class MissingSeries(NoSource):
    metric: Metric


class ProductSeries(BaseModel):
    id: UUID
    range: Range
    start: date  # `all` starts at the first point, or the first-seen day
    end: date  # today (UTC)
    series: list[Series | MissingSeries]


def day_end(day: date) -> datetime:
    """Values for day d use only captures before d + 1 00:00Z (DEC-031)."""
    return datetime.combine(day + timedelta(days=1), time(), UTC)


def coverage(
    session: Session, source_ids: Iterable[int], start: date | None, end: date
) -> tuple[set[date], dict[date, Literal["gap", "failed"]]]:
    """The days these sources collected, and the days they recorded a gap or failure instead."""
    where = [COVERAGE.c.source_id.in_(set(source_ids)), COVERAGE.c.day <= end]
    if start is not None:
        where.append(COVERAGE.c.day >= start)
    observed: set[date] = set()
    gaps: dict[date, Literal["gap", "failed"]] = {}
    for day, status in session.execute(select(COVERAGE.c.day, COVERAGE.c.status).where(*where)):
        if status in OBSERVED:
            observed.add(day)
        elif status in ("gap", "failed"):
            gaps[day] = status
    return observed, gaps


def build(
    metric: Metric,
    unit: Literal["usd_minor", "stores", "units_7d"],
    source: Source,
    as_of: datetime,
    points: list[Point],
    gaps: dict[date, Literal["gap", "failed"]],
    method: str | None = None,
) -> Series:
    seen = {p.day for p in points}
    return Series(
        metric=metric,
        unit=unit,
        source=source.key,
        source_name=source.name,
        method=method,
        as_of=as_of,
        stale=is_stale(source.config, as_of, datetime.now(UTC)),
        points=points,
        gaps=[SeriesGap(day=d, status=s) for d, s in sorted(gaps.items()) if d not in seen],
    )


def store_series(
    session: Session, product: Product, sources: dict[int, Source], start: date | None, end: date
) -> dict[str, Series | MissingSeries]:
    """Store count and the USD price band on each day a store source collected."""
    # ponytail: every snapshot of the product's store listings, so a day can carry each listing's
    # latest value (snapshots are change-only); a lateral "latest before start" if this gets slow.
    rows = session.execute(
        select(
            ListingSnapshot.listing_id,
            ListingSnapshot.captured_at,
            ListingSnapshot.price_min_minor,
            ListingSnapshot.price_max_minor,
            ListingSnapshot.currency,
            Listing.store_id,
            Listing.source_id,
            Listing.delisted_at,
        )
        .join(Listing, Listing.id == ListingSnapshot.listing_id)
        .where(
            Listing.product_id == product.id,
            Listing.store_id.is_not(None),
            ListingSnapshot.captured_at < day_end(end),
        )
        .order_by(ListingSnapshot.captured_at, ListingSnapshot.id)
    ).all()
    if not rows:
        none = "No store listing matched yet."
        return {
            "store_count": MissingSeries(metric="store_count", value=None, reason=none),
            "price": MissingSeries(metric="price", value=None, reason=none),
        }
    observed, gaps = coverage(session, {r.source_id for r in rows}, start, end)
    latest: dict[int, Row[Any]] = {}
    stores: list[Point] = []
    prices: list[Point] = []
    i = 0
    for day in sorted(observed):
        cutoff = day_end(day)
        while i < len(rows) and rows[i].captured_at < cutoff:
            latest[rows[i].listing_id] = rows[i]
            i += 1
        # ponytail: current membership and delisted_at; membership(t) replay arrives with M-5.
        live = [r for r in latest.values() if r.delisted_at is None or r.delisted_at >= cutoff]
        if live:
            as_of = max(r.captured_at for r in live)
            stores.append(
                Point(day=day, value=len({r.store_id for r in live}), high=None, as_of=as_of)
            )
        usd = [r for r in live if r.currency == "USD" and r.price_min_minor is not None]
        if usd:
            low = min(r.price_min_minor for r in usd)
            high = max(r.price_max_minor or r.price_min_minor for r in usd)
            prices.append(
                Point(day=day, value=low, high=high, as_of=max(r.captured_at for r in usd))
            )
    priced = [r for r in rows if r.currency == "USD" and r.price_min_minor is not None]
    return {
        "store_count": build(
            "store_count", "stores", sources[rows[-1].source_id], rows[-1].captured_at, stores, gaps
        ),
        "price": build(
            "price",
            "usd_minor",
            sources[priced[-1].source_id],
            priced[-1].captured_at,
            prices,
            gaps,
        )
        if priced
        else MissingSeries(metric="price", value=None, reason=NO_PRICE),
    }


def velocity_series(
    session: Session,
    product: Product,
    metric: Literal["velocity_js", "velocity_bumps"],
    sources: dict[int, Source],
    start: date | None,
    end: date,
) -> Series | MissingSeries:
    """V7 of one demand family per feature day, the newest feature version; never recomputed."""
    family = VELOCITY[metric]
    grade, key, method = FAMILIES[family]
    pdf = ProductDailyFeature
    rows = session.execute(
        select(pdf.feature_date, pdf.velocity_7d, pdf.computed_at)
        .where(pdf.product_id == product.id, pdf.family == family, pdf.feature_date <= end)
        .order_by(pdf.feature_date, pdf.feature_version.desc())
        .distinct(pdf.feature_date)
    ).all()
    if not rows:
        reason = f"No velocity computed from {method.split(',')[0]} yet."
        return MissingSeries(metric=metric, value=None, reason=reason)
    source = next(s for s in sources.values() if s.key == key)
    points = [
        Point(
            day=r.feature_date,
            value=round(r.velocity_7d),
            high=None,
            as_of=min(day_end(r.feature_date), r.computed_at),
        )
        for r in rows
        if r.velocity_7d is not None and (start is None or r.feature_date >= start)
    ]
    as_of = min(day_end(rows[-1].feature_date), rows[-1].computed_at)
    _, gaps = coverage(session, [source.id], start, end)
    return build(metric, "units_7d", source, as_of, points, gaps, f"{method} (grade {grade})")


@router.get(
    "/{product_id}/series",
    response_model=ProductSeries,
    responses={308: {"description": "Merged: the survivor's series URL, query string kept."}},
)
def get_product_series(
    product_id: UUID,
    request: Request,
    session: DB,
    range: Range = "90d",
    metrics: Annotated[
        str, Query(description=f"A comma list of {', '.join(METRICS)}; all by default.")
    ] = ",".join(METRICS),
) -> Response | ProductSeries:
    """The Trends tab (UX-5, DEC-245): one point per observed UTC day, never filled in."""
    requested = set(metrics.split(","))
    if not requested <= set(METRICS):
        raise APIError(
            422, "invalid_metrics", f"metrics takes a comma list of {', '.join(METRICS)}."
        )
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:  # like GET /v1/products/{id}, relative for /api too
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"../{product.merged_into_id}/series{query}", status_code=308)
    end = datetime.now(UTC).date()
    start = end - timedelta(days=DAYS[range] - 1) if range in DAYS else None
    sources = {s.id: s for s in session.scalars(select(Source))}
    built: dict[str, Series | MissingSeries] = {
        m: MissingSeries(metric=m, value=None, reason=MISSING[m]) for m in ("search", "ads")
    }
    if {"price", "store_count"} & requested:
        built |= store_series(session, product, sources, start, end)
    for metric in ("velocity_js", "velocity_bumps"):
        if metric in requested:
            built[metric] = velocity_series(session, product, metric, sources, start, end)
    series = [built[m] for m in METRICS if m in requested]
    if start is None:  # `all`: the real first date
        days = [p.day for s in series if isinstance(s, Series) for p in s.points]
        start = min([*days, product.first_seen_at.date()])
        for s in series:
            if isinstance(s, Series):
                s.gaps = [g for g in s.gaps if g.day >= start]
    return ProductSeries(id=product.id, range=range, start=start, end=end, series=series)
