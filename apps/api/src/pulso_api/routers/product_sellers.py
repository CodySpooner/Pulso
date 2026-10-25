"""The Sellers tab (UX-7): every store listing a product, its price spread and sellers (DEC-247)."""

import json
import statistics
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import Row, and_, func, select, true
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import Principal, current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB, is_stale
from pulso_api.schemas.provenance import NoSource
from pulso_core.models import (
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    Product,
    Source,
    Store,
    WorkspaceTrackedStore,
)
from pulso_core.money import convert_minor
from pulso_sources.fx_frankfurter import rate_as_of

router = APIRouter(prefix="/v1/products")
CATALOG = (
    "shopify_catalog"  # the one crawl that delists: a store's catalog target (shopify finalize)
)
NO_ADS = "No ad source yet: ad data arrives in Phase 8 or by CSV."
Unknown = Literal["store_blocked", "store_untrackable", "last_crawl_incomplete", "never_crawled"]
CURSOR = TypeAdapter(tuple[bool, AwareDatetime, int])


class SellerRow(BaseModel):
    listing_id: int
    url: str
    store_id: int
    domain: str
    platform: str
    tracked: bool  # this workspace tracks the store
    untrackable: bool  # headless or password-protected: left out of the spread
    price_usd_minor: int | None  # the lowest variant price at the snapshot's UTC-date FX rate
    price_minor: int | None  # as the store lists it
    price_max_minor: int | None  # a higher variant price, in the same currency: "from $x"
    currency: str | None
    fx_missing: bool  # a non-USD price with no FX rate for its date: never guessed
    started_at: AwareDatetime
    started_basis: Literal[
        "store", "first_seen"
    ]  # the store's created/published date, else Pulso's
    listed: Literal["listed", "delisted", "unknown"]
    delisted_at: AwareDatetime | None  # set only by a complete crawl that omitted the listing
    unknown_reason: Unknown | None
    last_seen: AwareDatetime
    stale: bool
    running_ads: NoSource
    source_name: str
    as_of: AwareDatetime | None  # the price snapshot's captured_at; null before any snapshot
    raw_payload_id: int | None


class SpreadPoint(BaseModel):
    domain: str
    price_usd_minor: int
    as_of: AwareDatetime


class Spread(BaseModel):
    """Current USD retail over active, trackable sellers: one price (the lowest) per store."""

    min: int | None
    p25: int | None
    median: int | None
    mean: int | None
    p75: int | None
    max: int | None
    n: int
    missing: int  # active stores left out: no price yet, or no FX rate for the snapshot's date
    untrackable: int  # active stores left out as untrackable (the footnote)
    points: list[SpreadPoint]  # bounded by the product's seller count (DEC-247)
    as_of: AwareDatetime | None


class Band(BaseModel):
    low: None
    high: None
    reason: Literal["needs_landed_cost"]  # the profitable half needs UX-8's engine and UX-10


class Counts(BaseModel):
    active: int  # stores with a listing no complete crawl has omitted
    delisted_30d: int
    new_14d: int  # stable panel: stores Pulso has had for 28 days, listing started in the last 14
    as_of: AwareDatetime | None


class SeriesDay(BaseModel):
    date: date
    active: int | None  # null on a gap day: never interpolated
    gap: bool  # no store catalog crawl succeeded that UTC day
    as_of: AwareDatetime | None  # the day's last successful catalog crawl


class Crawler(BaseModel):
    status: Literal["enabled", "disabled", "auto_disabled"]
    since: AwareDatetime | None
    reason: str | None


class SellersPage(BaseModel):
    rows: list[SellerRow]
    next_cursor: str | None = Field(description="Pass as `cursor` with the same filters.")
    spread: Spread
    band: Band
    counts: Counts
    series_90d: list[SeriesDay]
    crawler: Crawler
    as_of: AwareDatetime | None  # the newest time Pulso saw any of these sellers


@router.get(
    "/{product_id}/sellers",
    response_model=SellersPage,
    responses={308: {"description": "Merged: the survivor's sellers, query string kept."}},
)
def get_product_sellers(
    product_id: UUID,
    request: Request,
    session: DB,
    principal: Annotated[Principal, Depends(current_principal)],
    include_delisted: bool = False,
    new_14d: Annotated[
        bool, Query(description="Only the stable-panel sellers new in 14 days")
    ] = False,
    tracked: Annotated[bool, Query(description="Only stores this workspace tracks")] = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Response | SellersPage:
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:  # like GET /v1/products/{id} (DEC-238)
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"../{product.merged_into_id}/sellers{query}", status_code=308)
    after = None
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid sellers cursor.") from None
    now = datetime.now(UTC)
    source = session.scalars(select(Source).where(Source.key == "shopify_stores")).one()
    snap = (
        select(
            ListingSnapshot.price_min_minor,
            ListingSnapshot.price_max_minor,
            ListingSnapshot.currency,
            ListingSnapshot.captured_at,
            ListingSnapshot.raw_payload_id,
        )
        .where(ListingSnapshot.listing_id == Listing.id)
        .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
        .lateral()
    )
    crawl = (
        select(CollectorRunTarget.status)
        .where(
            CollectorRunTarget.scope == CATALOG,
            CollectorRunTarget.target_id == Store.domain,
            CollectorRunTarget.status != "pending",  # in flight, or left by a crashed run
        )
        .order_by(CollectorRunTarget.captured_at.desc())
        .limit(1)
        .lateral()
    )
    # ponytail: the whole seller set loads per request (a few hundred stores at most, vault
    # Design/Tables & Data Density), so the summary covers every row and keyset paging runs in
    # Python. Move the keyset into SQL if a product ever carries thousands of sellers.
    listings = session.execute(
        select(
            Listing,
            Store,
            snap,
            crawl.c.status.label("crawl"),
            WorkspaceTrackedStore.store_id.is_not(None).label("tracked"),
        )
        .join(Store, Store.id == Listing.store_id)
        .outerjoin(snap, true())
        .outerjoin(crawl, true())
        .outerjoin(
            WorkspaceTrackedStore,
            and_(
                WorkspaceTrackedStore.store_id == Store.id,
                WorkspaceTrackedStore.workspace_id == principal.workspace_id,
            ),
        )
        .where(Listing.product_id == product.id)
    ).all()
    rows = [seller(session, row, source, now) for row in listings]
    active = [row for row in rows if row.listed != "delisted"]
    panel = {r.Store.id for r in listings if r.Store.first_seen_at <= now - timedelta(days=28)}
    new = {
        r.listing_id
        for r in active
        if r.store_id in panel and r.started_at >= now - timedelta(days=14)
    }

    shown = [
        row
        for row in rows
        if (include_delisted or row.listed != "delisted")
        and (not new_14d or row.listing_id in new)
        and (not tracked or row.tracked)
    ]
    shown.sort(key=sort_key)
    if after is not None:
        shown = [row for row in shown if sort_key(row) > sort_key_of(after)]
    page = shown[:limit]
    next_cursor = None
    if len(shown) > limit:
        last = page[-1]
        next_cursor = json.dumps(
            [last.listed == "delisted", last.started_at.isoformat(), last.listing_id]
        )
    as_of = max((row.last_seen for row in rows), default=None)
    return SellersPage(
        rows=page,
        next_cursor=next_cursor,
        spread=spread(active),
        band=Band(low=None, high=None, reason="needs_landed_cost"),
        counts=Counts(
            active=len({row.store_id for row in active}),
            delisted_30d=len(
                {
                    row.store_id
                    for row in rows
                    if row.delisted_at is not None and row.delisted_at >= now - timedelta(days=30)
                }
            ),
            new_14d=len({row.store_id for row in active if row.listing_id in new}),
            as_of=as_of,
        ),
        series_90d=series(session, listings, now),
        crawler=Crawler(status="enabled", since=None, reason=None)
        if source.enabled
        else Crawler(
            status="auto_disabled" if source.status == "blocked" else "disabled",
            since=source.disabled_at,
            reason=source.disabled_reason,
        ),
        as_of=as_of,
    )


def seller(session: Session, row: Row[Any], source: Source, now: datetime) -> SellerRow:
    listing: Listing = row.Listing
    store: Store = row.Store
    usd, fx_missing = row.price_min_minor, False
    # ponytail: one rate lookup per non-USD row (US market, owner decision 3); cache per
    # (currency, day) if non-USD sellers ever dominate.
    if usd is not None and row.currency != "USD":
        rate = rate_as_of(session, row.currency, row.captured_at.astimezone(UTC).date())
        usd, fx_missing = (
            (None, True)
            if rate is None
            else (
                convert_minor(
                    usd, row.currency, "USD", rate.rate, rounding=ROUND_HALF_EVEN, inverse=True
                ),
                False,
            )
        )
    unknown: Unknown | None = None
    if listing.delisted_at is None:
        if store.status == "blocked":
            unknown = "store_blocked"
        elif store.status == "untrackable":
            unknown = "store_untrackable"
        elif row.crawl is None:
            unknown = "never_crawled"
        elif row.crawl != "success":
            unknown = "last_crawl_incomplete"  # partial or failed: never read as delisted
    store_date = listing.source_created_at or listing.source_published_at
    return SellerRow(
        listing_id=listing.id,
        url=listing.url,
        store_id=store.id,
        domain=store.domain,
        platform=store.platform,
        tracked=row.tracked,
        untrackable=store.status == "untrackable",
        price_usd_minor=usd,
        price_minor=row.price_min_minor,
        price_max_minor=row.price_max_minor,
        currency=row.currency,
        fx_missing=fx_missing,
        started_at=store_date or listing.first_seen_at,
        started_basis="store" if store_date else "first_seen",
        listed="delisted" if listing.delisted_at else "unknown" if unknown else "listed",
        delisted_at=listing.delisted_at,
        unknown_reason=unknown,
        last_seen=listing.last_seen_at,
        stale=is_stale(source.config, listing.last_seen_at, now),
        running_ads=NoSource(value=None, reason=NO_ADS),
        source_name=source.name,
        as_of=row.captured_at,
        raw_payload_id=row.raw_payload_id,
    )


def sort_key(row: SellerRow) -> tuple[bool, float, int]:
    """Active rows first, then the newest start, then the newest listing."""
    return row.listed == "delisted", -row.started_at.timestamp(), -row.listing_id


def sort_key_of(cursor: tuple[bool, datetime, int]) -> tuple[bool, float, int]:
    return cursor[0], -cursor[1].timestamp(), -cursor[2]


def spread(active: list[SellerRow]) -> Spread:
    trackable = [row for row in active if not row.untrackable]
    best: dict[int, SpreadPoint] = {}  # one dot per store, its lowest price
    for row in trackable:
        if row.price_usd_minor is not None and row.as_of is not None:
            point = SpreadPoint(
                domain=row.domain, price_usd_minor=row.price_usd_minor, as_of=row.as_of
            )
            if (
                row.store_id not in best
                or point.price_usd_minor < best[row.store_id].price_usd_minor
            ):
                best[row.store_id] = point
    points = sorted(best.values(), key=lambda point: point.price_usd_minor)
    prices = [point.price_usd_minor for point in points]
    stats: dict[str, int | None] = dict.fromkeys(("min", "p25", "median", "mean", "p75", "max"))
    if prices:
        p25, median, p75 = statistics.quantiles(prices, n=4, method="inclusive")
        stats = {
            "min": prices[0],
            "p25": round(p25),
            "median": round(median),
            "mean": round(statistics.fmean(prices)),
            "p75": round(p75),
            "max": prices[-1],
        }
    return Spread(
        **stats,
        n=len(prices),
        missing=len({row.store_id for row in trackable} - best.keys()),
        untrackable=len({row.store_id for row in active if row.untrackable}),
        points=points,
        as_of=max((point.as_of for point in points), default=None),
    )


def series(session: Session, listings: Sequence[Row[Any]], now: datetime) -> list[SeriesDay]:
    """Active stores at the end of each UTC day with a successful catalog crawl; gaps stay null."""
    start = now.date() - timedelta(days=89)
    day = func.date(func.timezone("UTC", CollectorRunTarget.captured_at))
    crawled: dict[date, datetime] = {
        row[0]: row[1]
        for row in session.execute(
            select(day, func.max(CollectorRunTarget.captured_at))
            .where(
                CollectorRunTarget.scope == CATALOG,
                CollectorRunTarget.status == "success",
                CollectorRunTarget.captured_at >= datetime.combine(start, time(), UTC),
            )
            .group_by(day)
        )
    }
    days = []
    for offset in range(90):
        d = start + timedelta(days=offset)
        end = datetime.combine(d + timedelta(days=1), time(), UTC)
        live = {
            r.Store.id
            for r in listings
            if r.Listing.first_seen_at < end
            and (r.Listing.delisted_at is None or r.Listing.delisted_at >= end)
        }
        seen = crawled.get(d)
        days.append(
            SeriesDay(
                date=d, active=None if seen is None else len(live), gap=seen is None, as_of=seen
            )
        )
    return days
