"""Daily Pulse (WF-6 part a, DEC-337): `GET /v1/pulse?date=`, the home dashboard's sections for
one UTC day. Every number reads only what was captured before the day's cutoff, d + 1 00:00Z
(DEC-031), so a past day replays as the data stood; a section nothing feeds says no_source and
its reason, never zeros (DEC-040). Read only. The page is WF-6b."""

import math
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any, Literal, Protocol
from uuid import UUID

from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Row, Select, bindparam, exists, func, or_, select, text, true
from sqlalchemy.orm import InstrumentedAttribute, Session, aliased
from sqlalchemy.sql import ColumnElement

import pulso_core
from pulso_api.auth import current_principal
from pulso_api.routers.alerts import AlertOut
from pulso_api.routers.products import DB, NO_SETTINGS, CurrentPrincipal
from pulso_api.routers.watchlists import lists, resolve
from pulso_core.landed_cost_loader import STOCK_READ, in_stock
from pulso_core.models import (
    Alert,
    Image,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    RawPayload,
    Score,
    ShippingOption,
    Source,
    Store,
    WatchlistItem,
    WorkspaceSettings,
    WorkspaceTrackedStore,
)
from pulso_core.scores import Stage
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.scores import opportunity as op

router = APIRouter(prefix="/v1/pulse", dependencies=[Depends(current_principal)])
Status = Literal["ok", "empty", "no_source"]
LIMIT = 10  # items per section and per watchlist (vault: "10 is a guess")
SERIES_DAYS = 14  # a watched product's sparkline (imp-421)
LAUNCH_DAYS = 7  # a launch is published at most this long before the cutoff (review M15)
# ponytail: caps that keep each query bounded; page them if a day ever outgrows one.
LISTS = 20  # watchlists summarised
CANDIDATES = 500  # products whose margin is re-costed for one day
DAY_ALERTS = 500  # a day's alerts read
EMERGING: tuple[Stage, ...] = ("emerging", "rising")


class Ref(BaseModel):
    id: UUID  # the survivor when the row's product was merged (DEC-263)
    name: str
    image_url: str | None


class Section(BaseModel):
    status: Status  # no_source: nothing feeds it on this day (DEC-040); empty: fed, nothing moved
    as_of: AwareDatetime | None  # the newest capture behind its items; null without items
    sources: list[str]  # the score kinds, view and sources.key it reads
    reason: str | None  # why it is empty or has no source; null when ok


class ScoreMove(BaseModel):
    """A Trend Score against the day before's newest row, both under one model_version."""

    old: float
    new: float
    change: float  # new − old, signed: the UI's ▲/▼
    as_of: AwareDatetime  # the newer row's inputs were captured before this


class Emerging(BaseModel):
    product: Ref
    value: float  # Trend Score v0 (Beta), 0–100
    stage: Stage  # emerging or rising
    since_yesterday: ScoreMove | None  # null with no comparable row the day before
    model_version: str
    as_of: AwareDatetime


class Mover(ScoreMove):
    product: Ref
    model_version: str


class Launch(BaseModel):
    listing_id: int
    product: Ref | None  # null until matching links the listing
    title: str
    store: str  # the store's domain
    published_at: AwareDatetime  # source_published_at, else source_created_at
    as_of: AwareDatetime  # first_seen_at: when the crawler first saw it


class TrendPoint(BaseModel):
    day: date
    value: float  # the day's newest Trend Score
    as_of: AwareDatetime


class WatchedProduct(BaseModel):
    product: Ref
    added_at: AwareDatetime  # the first add
    trend: ScoreMove | None  # since yesterday
    stage: Stage | None  # Lifecycle on the day
    stage_before: Stage | None  # the day before's; a different one means it changed stage
    alerts: list[str]  # types of the day's alerts on its supplier offers, e.g. back_in_stock
    series: list[
        TrendPoint
    ]  # Trend Score on the 14 days to the day, oldest first, scored days only


class WatchlistSummary(BaseModel):
    id: UUID
    name: str
    item_count: int  # every item now, before survivors merge
    as_of: AwareDatetime | None  # the newest point of its items
    items: list[WatchedProduct]  # the 10 added last


class MarginMove(BaseModel):
    """The best landed margin (the economics view, default scenario) at the day's cutoff against
    the day before's, under today's workspace settings."""

    product: Ref
    old_bps: int  # contribution before ads / price
    new_bps: int
    change_bps: int  # signed
    duty_not_set: bool  # costed at duty 0, as Opportunity reads it (DEC-331 b)
    supplier_listing_id: int | None  # the listing picked at the cutoff
    as_of: AwareDatetime  # the margin's oldest input at the cutoff


class SupplierMove(BaseModel):
    """A supplier offer whose price or stock changed on the day."""

    listing_id: int
    product: Ref | None
    title: str
    source: str
    currency: str | None  # of the prices; null without a price change
    old_price_minor: int | None
    new_price_minor: int | None
    price_change_pct: float | None  # signed
    was_in_stock: bool | None  # null without a stock change
    in_stock: bool | None
    raw_payload_id: int  # the newest change's capture
    as_of: AwareDatetime


class SearchMover(BaseModel):
    product: Ref
    slope: float  # ln((m4 + 1) / (m8 + 1)): the 4 latest complete weeks against the 8 before
    change_pct: float  # e^slope − 1, signed
    keywords: int  # its keywords with 12 complete weeks
    as_of: AwareDatetime  # the oldest Trends capture used


class EmergingSection(Section):
    items: list[Emerging]


class MoversSection(Section):
    items: list[Mover]


class LaunchSection(Section):
    items: list[Launch]


class AlertSection(Section):
    unread: int  # of the day's alerts
    items: list[AlertOut]  # unread first, then newest


class WatchlistSection(Section):
    items: list[WatchlistSummary]


class MarginSection(Section):
    items: list[MarginMove]  # biggest change first


class SupplierSection(Section):
    items: list[SupplierMove]  # stock flips first, then the biggest price change


class SearchSection(Section):
    items: list[SearchMover]  # biggest move either way first


class Sections(BaseModel):
    emerging: EmergingSection
    movers_up: MoversSection
    movers_down: MoversSection
    new_in_stores: LaunchSection
    alerts: AlertSection
    watchlists: WatchlistSection
    margins: MarginSection
    suppliers: SupplierSection
    search: SearchSection


class Pulse(BaseModel):
    day: date  # the UTC day
    cutoff: AwareDatetime  # day + 1 00:00Z: nothing captured from then on is read
    sections: Sections


class HasProduct(Protocol):
    @property
    def product(self) -> Ref: ...


def top[T: HasProduct](items: Iterable[T]) -> list[T]:
    """The first LIMIT items, one per surviving product."""
    seen: set[UUID] = set()
    found = []
    for item in items:
        if item.product.id not in seen:
            seen.add(item.product.id)
            found.append(item)
    return found[:LIMIT]


def built[S: Section](
    kind: type[S],
    items: Sequence[Any],
    fed: bool,
    sources: list[str],
    empty: str,
    none: str,
    as_of: datetime | None = None,
    **extra: Any,
) -> S:
    return kind(
        status="ok" if items else "empty" if fed else "no_source",
        as_of=as_of or max((i.as_of for i in items if i.as_of), default=None),
        sources=sources,
        reason=None if items else empty if fed else none,
        items=items,
        **extra,
    )


def refs(session: Session, product_ids: Iterable[UUID | None]) -> dict[UUID, Ref]:
    """Each product as a row shows it: its survivor (DEC-263)."""
    into = resolve(session, list({p for p in product_ids if p is not None}))
    if not into:
        return {}
    rows = session.execute(
        select(Product.id, Product.name, Image.url)
        .outerjoin(Image, Image.id == Product.main_image_id)
        .where(Product.id.in_(set(into.values())))
    )
    found = {id: Ref(id=id, name=name, image_url=url) for id, name, url in rows}
    return {product_id: found[survivor] for product_id, survivor in into.items()}


def newest(kind: str, days: Sequence[date], *where: ColumnElement[bool]) -> Select[Any]:
    """Each product's newest row per day: its latest computation, as `latest()` picks."""
    return (
        select(
            Score.product_id,
            Score.date,
            Score.value,
            Score.stage,
            Score.model_version,
            Score.computed_at,
        )
        .where(Score.kind == kind, Score.date.in_(days), *where)
        .order_by(
            Score.product_id, Score.date, Score.computed_at.desc(), Score.model_version.desc()
        )
        .distinct(Score.product_id, Score.date)
    )


def scored_at(row: Row[Any]) -> datetime:
    """A score row's inputs were captured before its day's cutoff, or its computation."""
    computed: datetime = row.computed_at
    return min(cutoff(row.date), computed)


def move(new: Row[Any] | None, old: Row[Any] | None) -> ScoreMove | None:
    if new is None or old is None or new.value is None or old.value is None:
        return None
    if new.model_version != old.model_version:  # a fix is a new version, never a move
        return None
    change = round(float(new.value - old.value), 1)
    return ScoreMove(
        old=float(old.value), new=float(new.value), change=change, as_of=scored_at(new)
    )


def scores(session: Session, day: date) -> tuple[EmergingSection, MoversSection, MoversSection]:
    """Top emerging (Trend Score among emerging or rising), and day-over-day movers."""
    # ponytail: ranks the day's scored products in Python; a SQL LIMIT per list past ~10k.
    yesterday = day - timedelta(days=1)
    rows = session.execute(newest("trend", [yesterday, day])).all()
    by = {(r.product_id, r.date): r for r in rows}
    today = [r for r in rows if r.date == day]
    stages = {r.product_id: r.stage for r in session.execute(newest("lifecycle", [day]))}
    rising = [r for r in today if r.value is not None and stages.get(r.product_id) in EMERGING]
    rising.sort(key=lambda r: (-r.value, str(r.product_id)))
    moves = {r.product_id: move(r, by.get((r.product_id, yesterday))) for r in today}
    moved = sorted(
        ((p, m, by[p, day].model_version) for p, m in moves.items() if m and m.change),
        key=lambda pmv: (-pmv[1].change, str(pmv[0])),
    )
    found = refs(session, [r.product_id for r in rising] + [p for p, _, _ in moved])
    emerging = [
        Emerging(
            product=found[r.product_id],
            value=float(r.value),
            stage=stages[r.product_id],
            since_yesterday=moves[r.product_id],
            model_version=r.model_version,
            as_of=scored_at(r),
        )
        for r in rising
    ]
    movers = [
        Mover(**m.model_dump(), product=found[p], model_version=version) for p, m, version in moved
    ]
    fed = bool(today)
    none = "No Trend Score for this day yet: the nightly job hasn't scored it."
    flat = "No Trend Score moved from the day before under the same model version."
    quiet = "No product scored emerging or rising on this day."
    up = top(m for m in movers if m.change > 0)
    down = top(m for m in reversed(movers) if m.change < 0)
    return (
        built(EmergingSection, top(emerging), fed, ["trend", "lifecycle"], quiet, none),
        built(MoversSection, up, fed, ["trend"], flat, none),
        built(MoversSection, down, fed, ["trend"], flat, none),
    )


def launches(session: Session, workspace_id: UUID, start: datetime, end: datetime) -> LaunchSection:
    """Listings first seen on the day in the workspace's tracked stores, launched recently, so a
    newly tracked store's back catalogue doesn't flood it (review M15)."""
    tracked = select(WorkspaceTrackedStore.store_id).where(
        WorkspaceTrackedStore.workspace_id == workspace_id
    )
    published = func.coalesce(Listing.source_published_at, Listing.source_created_at)
    rows = session.execute(
        select(
            Listing.id,
            Listing.product_id,
            Listing.title,
            Store.domain,
            published.label("published_at"),
            Listing.first_seen_at,
        )
        .join(Store, Store.id == Listing.store_id)
        .where(
            Listing.store_id.in_(tracked),
            Listing.first_seen_at >= start,
            Listing.first_seen_at < end,
            published >= end - timedelta(days=LAUNCH_DAYS),
            published < end,
        )
        .order_by(Listing.first_seen_at.desc(), Listing.id.desc())
        .limit(LIMIT)
    ).all()
    crawling = session.scalar(select(Source.enabled).where(Source.key == "shopify_stores"))
    tracking = session.scalar(select(tracked.exists()))
    found = refs(session, [r.product_id for r in rows])
    items = [
        Launch(
            listing_id=r.id,
            product=found.get(r.product_id) if r.product_id else None,
            title=r.title,
            store=r.domain,
            published_at=r.published_at,
            as_of=r.first_seen_at,
        )
        for r in rows
    ]
    none = "No tracked stores yet." if crawling else "The Shopify store crawler is off."
    return built(
        LaunchSection,
        items,
        bool(crawling and tracking),
        ["shopify_stores"],
        "No launch in your tracked stores on this day.",
        none,
    )


def day_alerts(session: Session, workspace_id: UUID, start: datetime, end: datetime) -> list[Alert]:
    """The workspace's alerts fired on the day and not archived: unread first, then newest."""
    return list(
        session.scalars(
            select(Alert)
            .where(
                Alert.workspace_id == workspace_id,
                Alert.archived_at.is_(None),
                Alert.fired_at >= start,
                Alert.fired_at < end,
            )
            .order_by(Alert.read_at.is_not(None), Alert.fired_at.desc(), Alert.id.desc())
            .limit(DAY_ALERTS)
        )
    )


def watchlists(
    session: Session, workspace_id: UUID, day: date, fired: list[Alert]
) -> WatchlistSection:
    """Each list's count and its 10 last-added products: a 14-day Trend Score series and what
    changed since yesterday (imp-421). Lists are as they stand now; the numbers are the day's."""
    summaries = lists(session, workspace_id)[:LISTS]
    place = (
        func.row_number()
        .over(
            partition_by=WatchlistItem.watchlist_id,
            order_by=(WatchlistItem.added_at.desc(), WatchlistItem.product_id.desc()),
        )
        .label("place")
    )
    ranked = (
        select(WatchlistItem.watchlist_id, WatchlistItem.product_id, WatchlistItem.added_at, place)
        .where(WatchlistItem.workspace_id == workspace_id)
        .subquery()
    )
    rows = session.execute(
        select(ranked.c.watchlist_id, ranked.c.product_id, ranked.c.added_at)
        .where(ranked.c.place <= LIMIT)
        .order_by(ranked.c.watchlist_id, ranked.c.place)
    ).all()
    found = refs(session, [r.product_id for r in rows])
    products = list({ref.id for ref in found.values()})
    days = [day - timedelta(days=i) for i in range(SERIES_DAYS)][::-1]
    series: defaultdict[UUID, list[Row[Any]]] = defaultdict(list)
    for r in session.execute(newest("trend", days, Score.product_id.in_(products))):
        series[r.product_id].append(r)
    stages = {
        (r.product_id, r.date): r.stage
        for r in session.execute(newest("lifecycle", days[-2:], Score.product_id.in_(products)))
    }
    offers = [int(a.entity_id) for a in fired if a.entity_type == "supplier_offer"]
    owners = dict(
        session.execute(select(Listing.id, Listing.product_id).where(Listing.id.in_(offers)))
        .tuples()
        .all()
    )
    of = refs(session, owners.values())
    chips: defaultdict[UUID, list[str]] = defaultdict(list)
    for a in fired:
        owner = owners.get(int(a.entity_id)) if a.entity_type == "supplier_offer" else None
        if owner is not None and a.type not in chips[of[owner].id]:
            chips[of[owner].id].append(a.type)

    def watched(product: Ref, added_at: datetime) -> WatchedProduct:
        points = series[product.id]
        last = {r.date: r for r in points}
        return WatchedProduct(
            product=product,
            added_at=added_at,
            trend=move(last.get(day), last.get(days[-2])),
            stage=stages.get((product.id, day)),
            stage_before=stages.get((product.id, days[-2])),
            alerts=chips[product.id],
            series=[
                TrendPoint(day=r.date, value=float(r.value), as_of=scored_at(r))
                for r in points
                if r.value is not None
            ],
        )

    held: defaultdict[UUID, list[WatchedProduct]] = defaultdict(list)
    for r in rows:
        held[r.watchlist_id].append(watched(found[r.product_id], r.added_at))
    items = []
    for summary in summaries:
        kept = top(held[summary.id])
        items.append(
            WatchlistSummary(
                id=summary.id,
                name=summary.name,
                item_count=summary.item_count,
                as_of=max((p.as_of for w in kept for p in w.series), default=None),
                items=kept,
            )
        )
    watching = [s for s in items if s.items]
    return built(
        WatchlistSection,
        items if watching else [],
        True,
        ["trend", "lifecycle", "alerts"],
        "Watch products with W to see them here.",
        "",
    )


@cache
def dated_economics() -> str:
    """The economics view (DEC-265, DEC-291) as of `:cutoff` for `:workspace_id` and `:ids`.

    Built from the live view's frozen text, as 0010 plans a dated reader: every observation table
    reads only captures before the cutoff (DEC-031), and a listing is live until its delisting
    time. That text is what the newest view revision (0014, 0023, ...: each edits its
    previous_view()) executes in upgrade(), so a new one is picked up on its own; a test holds
    this text, less those rewrites, to the live view (XR-67, DEC-349). ponytail: usd_rate()
    still picks FX by date alone, so a backfilled rate captured after the cutoff can price a
    non-USD line; every CJ price is USD.
    """
    migrations = ScriptDirectory(str(Path(pulso_core.__file__).parent / "migrations"))
    head = next(s.module for s in migrations.walk_revisions() if hasattr(s.module, "previous_view"))
    executed: list[str] = []
    head.__dict__["op"] = SimpleNamespace(execute=executed.append)  # Alembic's private copy
    head.upgrade()
    [created] = executed  # the view, and nothing else
    view = created.split(" AS\n", 1)[1]
    for table, alias, count in (("listing_snapshots", "snap", 3), ("shipping_options", "so", 2)):
        old = f"{table} {alias}"
        assert view.count(old) == count, old
        view = view.replace(old, f"(SELECT * FROM {table} WHERE captured_at < :cutoff) {alias}")
    view, n = re.subn(
        r"(\w+)\.delisted_at IS NULL",
        r"(\1.delisted_at IS NULL OR \1.delisted_at >= :cutoff)",
        view,
    )
    assert n == 3 and view.count("WHERE p.merged_into_id IS NULL") == 1
    return view.replace(
        "WHERE p.merged_into_id IS NULL",
        "WHERE p.merged_into_id IS NULL AND s.workspace_id = :workspace_id AND p.id IN :ids",
    )


def economics(
    session: Session, workspace_id: UUID, product_ids: list[UUID], at: datetime
) -> dict[UUID, Any]:
    query = text(f"SELECT * FROM ({dated_economics()}) economics").bindparams(
        bindparam("ids", expanding=True)
    )
    rows = session.execute(query, {"cutoff": at, "workspace_id": workspace_id, "ids": product_ids})
    return {row["product_id"]: row for row in rows.mappings()}


def touched(
    table: type[ListingSnapshot] | type[ShippingOption], start: datetime, end: datetime
) -> ColumnElement[bool]:
    """The listing has a capture on the day. LIMIT 1 keeps it one (listing_id, captured_at) index
    probe per listing: as EXISTS, the planner scans the whole table for the day's captures."""
    return (
        select(table.id)
        .where(table.listing_id == Listing.id, table.captured_at >= start, table.captured_at < end)
        .limit(1)
        .scalar_subquery()
        .is_not(None)
    )


def listed(session: Session, vendor: InstrumentedAttribute[int | None], end: datetime) -> bool:
    """Some store (or supplier) listing was seen before the cutoff."""
    seen = exists().where(vendor.is_not(None), Listing.first_seen_at < end)
    return bool(session.scalar(select(seen)))


def margins(session: Session, workspace_id: UUID, start: datetime, end: datetime) -> MarginSection:
    """Products whose best landed margin moved on the day: re-costed at both cutoffs under
    today's settings, so only market inputs (supplier price, freight, store price) move it."""
    settings = session.get(WorkspaceSettings, workspace_id)
    if settings is None:
        return built(MarginSection, [], False, [op.VIEW], "", NO_SETTINGS)
    store = aliased(Listing)
    changed = session.scalars(
        select(Listing.product_id)
        .where(
            Listing.product_id.is_not(None),
            or_(touched(ListingSnapshot, start, end), touched(ShippingOption, start, end)),
            # a margin needs a market price: a store listing (DEC-265)
            exists().where(store.product_id == Listing.product_id, store.store_id.is_not(None)),
        )
        .distinct()
        .limit(CANDIDATES)
    ).all()
    into = resolve(session, [p for p in changed if p is not None])
    ids = list(set(into.values()))
    items: list[MarginMove] = []
    if ids:
        found = refs(session, ids)
        now, then = (economics(session, workspace_id, ids, at) for at in (end, start))
        for product_id in ids:
            new = op.margin_of(now.get(product_id), settings)
            old = op.margin_of(then.get(product_id), settings)
            if new is None or old is None or new.bps is None or old.bps is None:
                continue
            if new.bps != old.bps:
                assert new.as_of is not None  # a margin has a supplier price behind it
                items.append(
                    MarginMove(
                        product=found[product_id],
                        old_bps=old.bps,
                        new_bps=new.bps,
                        change_bps=new.bps - old.bps,
                        duty_not_set=new.duty_not_set or old.duty_not_set,
                        supplier_listing_id=now[product_id]["supplier_listing_id"],
                        as_of=new.as_of,
                    )
                )
    items.sort(key=lambda m: (-abs(m.change_bps), str(m.product.id)))
    return built(
        MarginSection,
        top(items),
        listed(session, Listing.store_id, end) and listed(session, Listing.supplier_id, end),
        [op.VIEW],
        "No best landed margin moved on this day.",
        "No market price yet: a margin needs a store price and a supplier price.",
    )


def suppliers(session: Session, start: datetime, end: datetime) -> SupplierSection:
    """Supplier offers whose newest price, or in_stock() (DEC-243), at the cutoff differs from the
    newest before the day: what the alert rules watch (DEC-324), for every offer."""

    def last(before: datetime, stock: bool) -> Any:
        snap = ListingSnapshot
        # A snapshot without stock fields (CJ's catalog) says nothing about stock, and a CJ stock
        # capture's unknown total supersedes an older level (DEC-348, DEC-356).
        reads = STOCK_READ if stock else snap.price_min_minor.is_not(None)
        return (
            select(snap)
            .join(RawPayload, RawPayload.id == snap.raw_payload_id)
            .where(snap.listing_id == Listing.id, snap.captured_at < before, reads)
            .order_by(snap.captured_at.desc(), snap.id.desc())
            .limit(1)
            .lateral()
        )

    price, was, stock, had = (
        last(end, False),
        last(start, False),
        last(end, True),
        last(start, True),
    )
    rows = session.execute(
        select(
            Listing.id,
            Listing.product_id,
            Listing.title,
            Source.key,
            price.c.price_min_minor.label("price"),
            price.c.currency,
            price.c.captured_at.label("price_at"),
            price.c.raw_payload_id.label("price_payload"),
            was.c.price_min_minor.label("old_price"),
            was.c.currency.label("old_currency"),
            stock.c.available,
            stock.c.stock,
            stock.c.captured_at.label("stock_at"),
            stock.c.raw_payload_id.label("stock_payload"),
            had.c.available.label("old_available"),
            had.c.stock.label("old_stock"),
            had.c.captured_at.label("old_stock_at"),
        )
        .join(Source, Source.id == Listing.source_id)
        .outerjoin(price, true())
        .outerjoin(was, true())
        .outerjoin(stock, true())
        .outerjoin(had, true())
        .where(Listing.supplier_id.is_not(None), touched(ListingSnapshot, start, end))
    ).all()
    moved = []
    for r in rows:
        priced = (
            r.old_price is not None
            and r.price is not None
            and r.currency == r.old_currency
            and r.price != r.old_price
        )
        flipped = (
            r.old_stock_at is not None
            and r.stock_at is not None
            and in_stock(r.available, r.stock) != in_stock(r.old_available, r.old_stock)
        )
        if priced or flipped:
            moved.append((r, priced, flipped))
    found = refs(session, [r.product_id for r, _, _ in moved])
    items = [
        SupplierMove(
            listing_id=r.id,
            product=found.get(r.product_id) if r.product_id else None,
            title=r.title,
            source=r.key,
            currency=r.currency if priced else None,
            old_price_minor=r.old_price if priced else None,
            new_price_minor=r.price if priced else None,
            price_change_pct=round(100 * (r.price - r.old_price) / max(r.old_price, 1), 1)
            if priced
            else None,  # ponytail: a 0 price reads as 1, as the alert rules do
            was_in_stock=in_stock(r.old_available, r.old_stock) if flipped else None,
            in_stock=in_stock(r.available, r.stock) if flipped else None,
            raw_payload_id=max(
                (at, payload)
                for at, payload, used in (
                    (r.price_at, r.price_payload, priced),
                    (r.stock_at, r.stock_payload, flipped),
                )
                if used
            )[1],
            as_of=max(at for at, used in ((r.price_at, priced), (r.stock_at, flipped)) if used),
        )
        for r, priced, flipped in moved
    ]
    items.sort(key=lambda m: (m.in_stock is None, -abs(m.price_change_pct or 0), m.listing_id))
    sources = sorted({r.key for r in rows}) or ["cj"]
    return built(
        SupplierSection,
        items[:LIMIT],
        listed(session, Listing.supplier_id, end),
        sources,
        "No supplier price or stock changed on this day.",
        "No supplier offer observed yet.",
    )


def search(session: Session, day: date) -> SearchSection:
    """Products whose Trends interest moved most: the day's `gt_interest` feature rows (R-18),
    each the median slope of its confirmed keywords' newest 12-week capture (DEC-311)."""
    pdf = ProductDailyFeature
    slope = pdf.features["gt_slope"].as_float()
    rows = session.execute(
        select(
            pdf.product_id,
            slope.label("slope"),
            pdf.features["gt_keywords"].as_integer().label("keywords"),
            pdf.features["gt_as_of"].as_string().label("gt_as_of"),
        )
        .where(
            pdf.family == "gt_interest",
            pdf.feature_date == day,
            pdf.feature_version == FEATURE_VERSION,
        )
        .order_by(func.abs(slope).desc().nulls_last(), pdf.product_id)
        .limit(2 * LIMIT)  # room for merged duplicates
    ).all()
    moved = [r for r in rows if r.slope is not None and r.slope != 0]
    found = refs(session, [r.product_id for r in moved])
    items = [
        SearchMover(
            product=found[r.product_id],
            slope=r.slope,
            change_pct=round(100 * (math.exp(r.slope) - 1), 1),
            keywords=r.keywords,
            as_of=datetime.fromisoformat(r.gt_as_of),
        )
        for r in moved
    ]
    return built(
        SearchSection,
        top(items),
        bool(rows),
        ["google_trends"],
        "No product's search interest moved on this day.",
        "No search interest for this day: no confirmed keyword has 12 weeks of Trends.",
    )


def newest_day(session: Session) -> date:
    """The day of the newest score written, else yesterday. Nights are scored in day order
    (DEC-326 a), so that is the newest scored day; one step back along the primary key finds it,
    where max(date) reads every row. ponytail: a backfill run out of order shows its day until the
    next night."""
    found = session.scalar(select(Score.date).order_by(Score.id.desc()).limit(1))
    return found or datetime.now(UTC).date() - timedelta(days=1)


@router.get("", response_model=Pulse)
def get_pulse(
    principal: CurrentPrincipal,
    session: DB,
    day: Annotated[
        date | None,
        Query(alias="date", description="A UTC day; the newest day with stored scores if absent."),
    ] = None,
) -> Pulse:
    """The Daily Pulse for one UTC day (SPEC §6.1, DEC-337): each section with its own as_of,
    sources and status, at most 10 items, every number from captures before the cutoff."""
    day = day or newest_day(session)
    start, end = cutoff(day - timedelta(days=1)), cutoff(day)
    workspace_id = principal.workspace_id
    emerging, up, down = scores(session, day)
    fired = day_alerts(session, workspace_id, start, end)
    return Pulse(
        day=day,
        cutoff=end,
        sections=Sections(
            emerging=emerging,
            movers_up=up,
            movers_down=down,
            new_in_stores=launches(session, workspace_id, start, end),
            alerts=built(
                AlertSection,
                [AlertOut.model_validate(a) for a in fired[:LIMIT]],
                True,
                ["alerts"],
                "No alert fired on this day.",
                "",
                as_of=max((a.fired_at for a in fired), default=None),
                unread=sum(a.read_at is None for a in fired),
            ),
            watchlists=watchlists(session, workspace_id, day, fired),
            margins=margins(session, workspace_id, start, end),
            suppliers=suppliers(session, start, end),
            search=search(session, day),
        ),
    )
