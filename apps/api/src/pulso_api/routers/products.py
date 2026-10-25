"""Product resources (UX-3, UX-2, UX-4). Products are global market data, so auth applies and
no workspace filter; only notes, tags and the best margin (Settings) are the workspace's."""

import json
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy import (
    Double,
    Row,
    Select,
    and_,
    case,
    delete,
    distinct,
    exists,
    func,
    literal,
    select,
    true,
    tuple_,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql import ColumnElement
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.schemas.provenance import NoSource, Sourced, Stat
from pulso_api.schemas.text import NoNulStr
from pulso_core.landed_cost_loader import in_stock
from pulso_core.models import (
    Category,
    Image,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    ProductNote,
    ProductTag,
    RawPayload,
    Source,
    Store,
    Supplier,
    workspace_product_economics,
)

router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
categories_router = APIRouter(prefix="/v1/categories", dependencies=[Depends(current_principal)])
DB = Annotated[Session, Depends(get_db)]
NO_PRICE = "No USD retail price observed yet."
NO_SIGNAL = "No demand family has a 7-day growth yet."  # the UI reads "Insufficient signal"
NO_SETTINGS = "No workspace settings yet."
MARGIN = "Landed cost, default scenario: price - landed cost - fees - returns, before ads"
NEEDS = {  # landed_cost.MISSING: what a margin needs, as the Profit tab words it
    "price_missing": "a market price",
    "supplier_cost_missing": "a supplier price",
    "freight_missing": "a freight quote",
    "freight_variant_mismatch": "a freight quote for this variant",
    "duty_not_set": "a duty rate",
    "fx_missing": "a USD exchange rate",
    "amount_out_of_range": "smaller amounts",
}
# Demand families that carry units, best grade first (vault Intelligence/Demand Signals).
# gt_slope is keyword-level, never a velocity.
FAMILIES = {
    "shp_inv": ("A", "shopify_stores", "Shopify inventory drops"),
    "shp_bump": ("B", "shopify_stores", "Shopify updated_at bumps, a lower bound"),
    "cj_stock": ("unproven", "cj", "CJ warehouse stock drops"),
}


class ProductHeader(BaseModel):
    id: UUID
    title: str
    image_url: str | None
    category: str | None  # the taxonomy path; null while uncategorised
    first_seen_at: AwareDatetime
    currency: Literal["USD"]  # of the *_minor stats
    store_count: Stat
    supplier_count: Stat
    price_min_minor: Stat  # lowest live retail price across store listings
    price_max_minor: Stat


class Velocity(Sourced):
    """V7 (units/7d) of the product's best-graded demand family on its latest feature day."""

    family: str  # product_daily_features.family, e.g. "shp_bump"
    grade: Literal["A", "B", "unproven"]
    growth: float  # G7 = ln((V7 + 5) / (V7 a week earlier + 5)): the momentum sort key (DEC-040)
    gap: bool  # the window overlaps a collection gap


class Margin(Sourced):
    """The best complete supplier's margin in the default scenario (DEC-265): the break-even CPA.
    As of its oldest input, whose source it names (DEC-259 e); stale when any input is."""

    margin_bps: int
    supplier_listing_id: int


class Incomplete(NoSource):
    """No complete cost row: R-16 withholds the margin and names what it needs."""

    missing: list[str]  # landed_cost.MISSING codes; empty when the workspace has no settings


class DiscoverItem(ProductHeader):
    velocity: Velocity | NoSource
    best_margin_minor: Margin | Incomplete
    as_of: AwareDatetime | None  # the oldest family feeding the card; null when nothing does
    stale: bool  # some family feeding the card is past twice its source's interval


class Degraded(BaseModel):
    source: str
    source_name: str
    state: Literal["blocked", "disabled", "stale"]
    since: AwareDatetime | None  # disabled_at, or the last capture of a stale source


class Vendor(BaseModel):
    id: int
    name: str  # a store's domain, a supplier's name


class DiscoverPage(BaseModel):
    items: list[DiscoverItem]
    next_cursor: str | None = Field(
        description="Pass as `cursor` with the same sort for the next page."
    )
    as_of: AwareDatetime | None  # the newest capture of a source feeding the feed
    degraded: list[Degraded]  # sources feeding the feed that are blocked, disabled or stale
    # The filters' store and supplier, named for their chips; null unfiltered or for an unknown id.
    store: Vendor | None
    supplier: Vendor | None


class CategoryOption(BaseModel):
    id: int
    path: str


def is_stale(config: dict[str, Any], as_of: datetime, now: datetime) -> bool:
    interval = config.get("expected_interval")  # seconds; without one a source is never stale
    return isinstance(interval, int) and now - as_of > timedelta(seconds=2 * interval)


def stat(
    row: Row[Any] | None, value: Callable[[Row[Any]], int], reason: str, now: datetime
) -> Stat:
    """The value from `row`, a listing's latest snapshot, with that snapshot's provenance."""
    if row is None:
        return NoSource(value=None, reason=reason)
    return Sourced(
        value=value(row),
        source=row.key,
        source_name=row.name,
        as_of=row.captured_at,
        raw_payload_id=row.raw_payload_id,
        stale=is_stale(row.config, row.captured_at, now),
    )


def latest_snapshots(session: Session, product_ids: Sequence[UUID]) -> dict[UUID, list[Row[Any]]]:
    """The latest snapshot of each live listing of these products: what every listing stat uses."""
    rows = session.execute(
        select(
            Listing.product_id,
            Listing.store_id,
            Listing.supplier_id,
            ListingSnapshot.captured_at,
            ListingSnapshot.raw_payload_id,
            ListingSnapshot.price_min_minor,
            ListingSnapshot.price_max_minor,
            ListingSnapshot.currency,
            ListingSnapshot.available,
            ListingSnapshot.stock,
            Source.key,
            Source.name,
            Source.config,
        )
        .join(Listing, Listing.id == ListingSnapshot.listing_id)
        .join(Source, Source.id == Listing.source_id)
        .where(Listing.product_id.in_(product_ids), Listing.delisted_at.is_(None))
        .order_by(
            ListingSnapshot.listing_id,
            ListingSnapshot.captured_at.desc(),
            ListingSnapshot.id.desc(),
        )
        .distinct(ListingSnapshot.listing_id)
    ).all()
    grouped: dict[UUID, list[Row[Any]]] = defaultdict(list)
    for row in rows:
        grouped[row.product_id].append(row)
    return grouped


def newest(group: list[Row[Any]]) -> Row[Any] | None:
    return max(group, key=lambda row: row.captured_at, default=None)


def low(row: Row[Any]) -> int:
    return int(row.price_min_minor)


def usd_priced(rows: list[Row[Any]]) -> list[Row[Any]]:
    # ponytail: USD prices only (US market, owner decision 3); others wait for an FX basis.
    return [row for row in rows if row.currency == "USD" and row.price_min_minor is not None]


def listing_stats(rows: list[Row[Any]], now: datetime) -> dict[str, Stat]:
    stores = [row for row in rows if row.store_id is not None]
    suppliers = [row for row in rows if row.supplier_id is not None]
    priced = usd_priced(stores)

    def high(row: Row[Any]) -> int:
        return int(row.price_max_minor if row.price_max_minor is not None else row.price_min_minor)

    return {
        "store_count": stat(
            newest(stores),
            lambda _: len({row.store_id for row in stores}),
            "No store listing matched yet.",
            now,
        ),
        "supplier_count": stat(
            newest(suppliers),
            lambda _: len({row.supplier_id for row in suppliers}),
            "No supplier listing matched yet.",
            now,
        ),
        "price_min_minor": stat(min(priced, key=low, default=None), low, NO_PRICE, now),
        "price_max_minor": stat(max(priced, key=high, default=None), high, NO_PRICE, now),
    }


def best_feature(product_id: InstrumentedAttribute[UUID] | UUID) -> Select[Any]:
    """The latest feature day with a growth, then the best-graded family on it (DEC-239 c)."""
    pdf = ProductDailyFeature
    rank = case({family: i for i, family in enumerate(FAMILIES)}, value=pdf.family)
    return (
        select(
            pdf.family,
            pdf.velocity_7d,
            pdf.growth_7d.label("growth"),
            pdf.has_gap,
            pdf.feature_date,
            pdf.computed_at,
        )
        .where(
            pdf.product_id == product_id,
            pdf.family.in_(FAMILIES),
            pdf.velocity_7d.is_not(None),
            pdf.growth_7d.is_not(None),
        )
        .order_by(pdf.feature_date.desc(), rank, pdf.feature_version.desc())
        .limit(1)
    )


def best_margins(
    session: Session, workspace_id: UUID, product_ids: Sequence[UUID]
) -> dict[UUID, RowMapping]:
    """The workspace's workspace_product_economics rows: the read behind every best margin."""
    view = workspace_product_economics.c
    rows = session.execute(
        select(workspace_product_economics).where(
            view.workspace_id == workspace_id, view.product_id.in_(product_ids)
        )
    ).mappings()
    return {row["product_id"]: row for row in rows}


def margin_stat(
    row: RowMapping | None, sources: dict[str, Source], now: datetime
) -> Margin | Incomplete:
    """A workspace_product_economics row as the best-margin stat; only a complete row has one."""
    if row is None:
        return Incomplete(value=None, reason=NO_SETTINGS, missing=[])
    if not row["complete"]:
        needs = [NEEDS[code] for code in row["missing"]]
        words = ", ".join(needs[:-1]) + " and " + needs[-1] if len(needs) > 1 else needs[0]
        return Incomplete(value=None, reason=f"Needs {words}.", missing=row["missing"])
    observed = sorted(
        (datetime.fromisoformat(trace["as_of"]), name, trace)
        for name, trace in row["sources"].items()
        if trace["as_of"] is not None
    )
    as_of, _, oldest = observed[0]
    return Margin(
        value=row["margin_minor"],
        source=oldest["source"],
        source_name=sources[oldest["source"]].name,
        as_of=as_of,
        raw_payload_id=oldest["raw_payload_id"],
        method=MARGIN,
        stale=any(is_stale(sources[t["source"]].config, at, now) for at, _, t in observed),
        margin_bps=row["margin_bps"],
        supplier_listing_id=row["supplier_listing_id"],
    )


def velocity_stat(
    row: Row[Any] | None, sources: dict[str, Source], now: datetime
) -> Velocity | NoSource:
    """A `best_feature` row as the velocity stat; none, or a null family, is no signal."""
    if row is None or row.family is None:
        return NoSource(value=None, reason=NO_SIGNAL)
    grade, key, method = FAMILIES[row.family]
    # Features for day d use only captures before d+1 00:00Z (DEC-031).
    as_of = min(
        datetime.combine(row.feature_date + timedelta(days=1), time(), UTC), row.computed_at
    )
    return Velocity(
        value=round(row.velocity_7d),
        source=key,
        source_name=sources[key].name,
        as_of=as_of,
        raw_payload_id=None,
        method=method,
        stale=is_stale(sources[key].config, as_of, now),
        family=row.family,
        grade=grade,
        growth=row.growth,
        gap=row.has_gap,
    )


Sort = Literal["momentum", "newest", "fewest_sellers"]
CURSORS: dict[str, TypeAdapter[Any]] = {
    "momentum": TypeAdapter(tuple[float | None, UUID]),  # null: insufficient signal
    "newest": TypeAdapter(tuple[AwareDatetime, UUID]),
    "fewest_sellers": TypeAdapter(tuple[Annotated[int, Field(ge=0, le=2**63 - 1)], UUID]),
}


@router.get("", response_model=DiscoverPage)
def list_products(
    session: DB,
    principal: Annotated[Principal, Depends(current_principal)],
    sort: Sort = "momentum",
    # Bounded by the column types (int4, BIGINT), so a huge value is a 422, not a 500 (XR-18).
    category: Annotated[int | None, Query(ge=1, le=2**31 - 1)] = None,
    price_min: Annotated[
        int | None, Query(ge=0, le=2**63 - 1, description="USD minor units")
    ] = None,
    price_max: Annotated[
        int | None, Query(ge=0, le=2**63 - 1, description="USD minor units")
    ] = None,
    source: Annotated[str | None, Query(max_length=80, description="A sources.key")] = None,
    # A query string arrives as text; the Literal needs the int.
    first_seen_days: Annotated[Literal[7, 30, 90] | None, BeforeValidator(int), Query()] = None,
    has_sellers: bool | None = None,
    store: Annotated[
        int | None, Query(ge=1, le=2**63 - 1, description="A stores.id: its live listings")
    ] = None,
    supplier: Annotated[
        int | None, Query(ge=1, le=2**63 - 1, description="A suppliers.id: its live listings")
    ] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 48,
) -> DiscoverPage:
    """Discover (UX-2): products neither merged nor emptied by an undo, filtered, sorted and
    keyset-paginated (DEC-239, DEC-271). An unknown store or supplier lists nothing (DEC-300)."""
    now = datetime.now(UTC)
    snap = (
        select(
            ListingSnapshot.price_min_minor,
            ListingSnapshot.price_max_minor,
            ListingSnapshot.currency,
        )
        .where(ListingSnapshot.listing_id == Listing.id)
        .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
        .lateral()
    )
    usd_store = and_(Listing.store_id.is_not(None), snap.c.currency == "USD")
    # The same rows as latest_snapshots, aggregated for filters and sorts over the whole set.
    listings = (
        select(
            func.count(distinct(Listing.store_id)).label("store_count"),
            func.min(snap.c.price_min_minor).filter(usd_store).label("price_low"),
            func.max(func.coalesce(snap.c.price_max_minor, snap.c.price_min_minor))
            .filter(usd_store)
            .label("price_high"),
        )
        .select_from(Listing)
        .join(snap, true())
        .where(Listing.product_id == Product.id, Listing.delisted_at.is_(None))
        .lateral()
    )
    feature = best_feature(Product.id).lateral()
    where: list[ColumnElement[bool]] = [Product.merged_into_id.is_(None), Product.status != "empty"]
    if category is not None:
        where.append(Product.category_id == category)
    if first_seen_days is not None:
        where.append(Product.first_seen_at >= now - timedelta(days=first_seen_days))
    vendors: list[ColumnElement[bool]] = []
    if source is not None:
        vendors.append(
            Listing.source_id == select(Source.id).where(Source.key == source).scalar_subquery()
        )
    if store is not None:
        vendors.append(Listing.store_id == store)  # ix_listings_store_id
    if supplier is not None:
        vendors.append(Listing.supplier_id == supplier)  # ix_listings_supplier_id
    where += [
        exists().where(Listing.product_id == Product.id, Listing.delisted_at.is_(None), vendor)
        for vendor in vendors
    ]
    feed = (
        select(
            Product.id,
            Product.name,
            Product.first_seen_at,
            Image.url.label("image_url"),
            Category.path.label("category"),
            listings.c.store_count,
            listings.c.price_low,
            listings.c.price_high,
            feature.c.family,
            feature.c.velocity_7d,
            feature.c.growth,
            feature.c.has_gap,
            feature.c.feature_date,
            feature.c.computed_at,
        )
        .select_from(Product)
        .join(listings, true())
        .outerjoin(feature, true())
        .outerjoin(Image, Image.id == Product.main_image_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(*where)
        .subquery()
    )
    filters: list[ColumnElement[bool]] = []
    if price_min is not None:
        filters.append(feed.c.price_high >= price_min)  # the price band overlaps the range
    if price_max is not None:
        filters.append(feed.c.price_low <= price_max)
    if has_sellers is not None:
        filters.append(feed.c.store_count > 0 if has_sellers else feed.c.store_count == 0)
    key = {
        "momentum": func.coalesce(feed.c.growth, literal(float("-inf"), Double)),
        "newest": feed.c.first_seen_at,
        "fewest_sellers": feed.c.store_count,
    }[sort]
    ascending = sort == "fewest_sellers"
    if cursor is not None:
        try:
            after, after_id = CURSORS[sort].validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid product cursor.") from None
        after = float("-inf") if after is None else after
        position = tuple_(key, feed.c.id)
        filters.append(position > (after, after_id) if ascending else position < (after, after_id))
    order = (key.asc(), feed.c.id.asc()) if ascending else (key.desc(), feed.c.id.desc())
    rows = session.execute(select(feed).where(*filters).order_by(*order).limit(limit + 1)).all()
    page = rows[:limit]

    sources = session.execute(
        select(
            Source,
            select(func.max(RawPayload.captured_at))
            .where(RawPayload.source_id == Source.id)
            .scalar_subquery()
            .label("last_capture"),
            exists()
            .where(Listing.source_id == Source.id, Listing.product_id.is_not(None))
            .label("feeding"),
        ).order_by(Source.id)
    ).all()
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        value = {
            "momentum": last.growth,
            "newest": last.first_seen_at.isoformat(),
            "fewest_sellers": last.store_count,
        }[sort]
        next_cursor = json.dumps([value, str(last.id)])
    snapshots = latest_snapshots(session, [row.id for row in page])
    margins = best_margins(session, principal.workspace_id, [row.id for row in page])
    by_key = {row.Source.key: row.Source for row in sources}
    feeding = [row for row in sources if row.feeding]
    degraded = []
    for row in feeding:
        source_row: Source = row.Source
        if source_row.status == "blocked" or not source_row.enabled:
            state: Literal["blocked", "disabled", "stale"] = (
                "blocked" if source_row.status == "blocked" else "disabled"
            )
            degraded.append(
                Degraded(
                    source=source_row.key,
                    source_name=source_row.name,
                    state=state,
                    since=source_row.disabled_at,
                )
            )
        elif row.last_capture is not None and is_stale(source_row.config, row.last_capture, now):
            degraded.append(
                Degraded(
                    source=source_row.key,
                    source_name=source_row.name,
                    state="stale",
                    since=row.last_capture,
                )
            )
    store_row = session.get(Store, store) if store is not None else None
    supplier_row = session.get(Supplier, supplier) if supplier is not None else None
    return DiscoverPage(
        items=[item(row, snapshots[row.id], margins.get(row.id), by_key, now) for row in page],
        next_cursor=next_cursor,
        as_of=max((row.last_capture for row in feeding if row.last_capture), default=None),
        degraded=degraded,
        store=Vendor(id=store_row.id, name=store_row.domain) if store_row else None,
        supplier=Vendor(id=supplier_row.id, name=supplier_row.name) if supplier_row else None,
    )


def item(
    row: Row[Any],
    snapshots: list[Row[Any]],
    economics: RowMapping | None,
    sources: dict[str, Source],
    now: datetime,
) -> DiscoverItem:
    stats = listing_stats(snapshots, now)
    velocity = velocity_stat(row, sources, now)
    margin = margin_stat(economics, sources, now)
    # Each family's newest capture: stores (and their prices), suppliers, demand; the margin's
    # oldest input.
    fed = [
        s
        for s in (stats["store_count"], stats["supplier_count"], velocity, margin)
        if isinstance(s, Sourced)
    ]
    return DiscoverItem(
        id=row.id,
        title=row.name,
        image_url=row.image_url,
        category=row.category,
        first_seen_at=row.first_seen_at,
        currency="USD",
        **stats,
        velocity=velocity,
        best_margin_minor=margin,
        as_of=min((s.as_of for s in fed), default=None),
        stale=any(s.stale for s in fed),
    )


@categories_router.get("", response_model=list[CategoryOption])
def list_categories(session: DB) -> list[CategoryOption]:
    """Categories that hold a product Discover lists: Discover's category filter."""
    used = exists().where(
        Product.category_id == Category.id,
        Product.merged_into_id.is_(None),
        Product.status != "empty",
    )
    rows = session.execute(select(Category.id, Category.path).where(used).order_by(Category.path))
    return [CategoryOption(id=row.id, path=row.path) for row in rows]


@router.get(
    "/{product_id}",
    response_model=ProductHeader,
    responses={308: {"description": "Merged: the survivor's URL, query string kept."}},
)
def get_product(product_id: UUID, request: Request, session: DB) -> Response | ProductHeader:
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:
        # Relative, so it resolves under the web app's /api rewrite too. A chained merge
        # redirects again.
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{product.merged_into_id}{query}", status_code=308)
    if product.status == "empty":  # an undo took its last listing (DEC-271)
        raise APIError(404, "no_listings", "This product has no listings left.")
    return ProductHeader(
        id=product.id,
        title=product.name,
        image_url=session.scalar(select(Image.url).where(Image.id == product.main_image_id)),
        category=session.scalar(select(Category.path).where(Category.id == product.category_id)),
        first_seen_at=product.first_seen_at,
        currency="USD",
        **listing_stats(latest_snapshots(session, [product.id])[product.id], datetime.now(UTC)),
    )


class SupplierCost(Sourced):
    """The lowest current unit cost among in-stock supplier offers."""

    platform: str  # suppliers.platform of that offer, e.g. "cj"


class Appearance(BaseModel):
    vendor: Literal["store", "supplier"]
    count: Stat  # stores: distinct live stores; suppliers: live offers (CJ has one supplier row)


class ProductOverview(BaseModel):
    """The Overview tab's key stats and where the product appears (UX-4, DEC-243)."""

    currency: Literal["USD"]  # of the *_minor stats
    price_min_minor: Stat
    price_median_minor: Stat  # the lower median of the USD store listings' lowest prices
    price_max_minor: Stat
    best_supplier_cost_minor: SupplierCost | NoSource
    landed_margin_minor: Margin | Incomplete  # Discover's best margin for this product (imp-280)
    first_seen_at: AwareDatetime
    age_days: Stat  # UTC days since first_seen_at, traced to the product's first observation
    velocity: Velocity | NoSource
    appearances: list[Appearance]  # one per source with a live listing, suppliers first
    ad_count: NoSource


def live_product(session: Session, product_id: UUID) -> Product:
    """A product a sub-resource may read or write. The page asks with the id `get_product`
    resolved, so a merged id here means a merge landed while the page was open."""
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:
        raise APIError(409, "merged", "This product was merged into another one. Reload the page.")
    return product


def appearance(store: bool, group: list[Row[Any]], now: datetime) -> Appearance:
    """One source's live listings of a product, counted as stores or as supplier offers."""
    n = len({row.store_id for row in group}) if store else len(group)
    return Appearance(
        vendor="store" if store else "supplier", count=stat(newest(group), lambda _: n, "", now)
    )


@router.get("/{product_id}/overview", response_model=ProductOverview)
def get_product_overview(
    product_id: UUID, session: DB, principal: Annotated[Principal, Depends(current_principal)]
) -> ProductOverview:
    product = live_product(session, product_id)
    now = datetime.now(UTC)
    rows = latest_snapshots(session, [product.id])[product.id]
    stats = listing_stats(rows, now)
    prices = sorted(usd_priced([row for row in rows if row.store_id is not None]), key=low)
    # Known out of stock is out; CJ's catalog reports no stock, so its offers count (DEC-243).
    offers = [
        row
        for row in usd_priced([row for row in rows if row.supplier_id is not None])
        if in_stock(row.available, row.stock)
    ]
    best = min(offers, key=low, default=None)
    cost: SupplierCost | NoSource = NoSource(value=None, reason="No in-stock supplier offer yet.")
    if best is not None:
        platform = session.scalar(select(Supplier.platform).where(Supplier.id == best.supplier_id))
        cost = SupplierCost(**stat(best, low, "", now).model_dump(), platform=platform)
    groups: dict[tuple[bool, str], list[Row[Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.store_id is not None, row.key)].append(row)
    # Suppliers first, then by source.
    appearances = [appearance(store, group, now) for (store, _), group in sorted(groups.items())]
    first = session.execute(
        select(ListingSnapshot.captured_at, ListingSnapshot.raw_payload_id, Source.key, Source.name)
        .join(Listing, Listing.id == ListingSnapshot.listing_id)
        .join(Source, Source.id == Listing.source_id)
        .where(Listing.product_id == product.id)
        .order_by(ListingSnapshot.captured_at, ListingSnapshot.id)
        .limit(1)
    ).first()
    age: Stat = NoSource(value=None, reason="No listing observation yet.")
    if first is not None:
        age = Sourced(
            value=(now.date() - product.first_seen_at.astimezone(UTC).date()).days,
            source=first.key,
            source_name=first.name,
            as_of=first.captured_at,
            raw_payload_id=first.raw_payload_id,
            stale=False,  # an age never goes stale
        )
    feature = session.execute(best_feature(product.id)).first()
    sources = {source.key: source for source in session.scalars(select(Source))}
    return ProductOverview(
        currency="USD",
        price_min_minor=stats["price_min_minor"],
        price_median_minor=stat(
            prices[(len(prices) - 1) // 2] if prices else None, low, NO_PRICE, now
        ),
        price_max_minor=stats["price_max_minor"],
        best_supplier_cost_minor=cost,
        landed_margin_minor=margin_stat(
            best_margins(session, principal.workspace_id, [product.id]).get(product.id),
            sources,
            now,
        ),
        first_seen_at=product.first_seen_at,
        age_days=age,
        velocity=velocity_stat(feature, sources, now),
        appearances=appearances,
        ad_count=NoSource(value=None, reason="No ad source is connected yet."),
    )


# Notes and tags: this workspace's own context on a product (the page's context rail, DEC-243).
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
NOTE_CURSOR = TypeAdapter(tuple[AwareDatetime, UUID])
Tag = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: Annotated[
        NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=10_000)
    ]


class Note(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    body: str
    created_at: AwareDatetime


class NotePage(BaseModel):
    items: list[Note]  # newest first
    next_cursor: str | None = Field(description="Pass as `cursor` for the next, older page.")


class Tags(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: Annotated[list[Tag], Field(max_length=20)]


class TagList(BaseModel):
    """The tags read back. A merge can join two products' tags past 20 (DEC-263)."""

    tags: list[str]


def with_merged(product_id: UUID) -> Select[tuple[UUID]]:
    """The product and every product merged into it, at any depth. A merge leaves notes and
    tags where they were, and the survivor reads them through merged_into_id (DEC-263)."""
    tree = select(Product.id).where(Product.id == product_id).cte("merged_tree", recursive=True)
    tree = tree.union(select(Product.id).where(Product.merged_into_id == tree.c.id))
    return select(tree.c.id)


@router.get("/{product_id}/notes", response_model=NotePage)
def list_product_notes(
    product_id: UUID,
    principal: CurrentPrincipal,
    session: DB,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> NotePage:
    live_product(session, product_id)
    query = select(ProductNote).where(
        ProductNote.workspace_id == principal.workspace_id,
        ProductNote.product_id.in_(with_merged(product_id)),
    )
    if cursor is not None:
        try:
            after = NOTE_CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid note cursor.") from None
        query = query.where(tuple_(ProductNote.created_at, ProductNote.id) < after)
    notes = session.scalars(
        query.order_by(ProductNote.created_at.desc(), ProductNote.id.desc()).limit(limit + 1)
    ).all()
    last = notes[limit - 1] if len(notes) > limit else None
    return NotePage(
        items=[Note.model_validate(note) for note in notes[:limit]],
        next_cursor=json.dumps([last.created_at.isoformat(), str(last.id)]) if last else None,
    )


@router.post("/{product_id}/notes", response_model=Note, status_code=201)
def create_product_note(
    product_id: UUID, note: NoteIn, principal: CurrentPrincipal, session: DB
) -> Note:
    live_product(session, product_id)
    row = ProductNote(
        workspace_id=principal.workspace_id,
        product_id=product_id,
        author_id=principal.user_id,
        body=note.body,
    )
    session.add(row)
    session.commit()
    return Note.model_validate(row)


def tags_of(session: Session, workspace_id: UUID, product_id: UUID) -> TagList:
    """Tags on the product and on products merged into it, one per case-insensitive spelling."""
    unique: dict[str, str] = {}
    for tag in sorted(
        session.scalars(
            select(ProductTag.tag).where(
                ProductTag.workspace_id == workspace_id,
                ProductTag.product_id.in_(with_merged(product_id)),
            )
        ),
        key=lambda tag: (tag.casefold(), tag),
    ):
        unique.setdefault(tag.casefold(), tag)
    return TagList(tags=list(unique.values()))


@router.get("/{product_id}/tags", response_model=TagList)
def list_product_tags(product_id: UUID, principal: CurrentPrincipal, session: DB) -> TagList:
    live_product(session, product_id)
    return tags_of(session, principal.workspace_id, product_id)


@router.put("/{product_id}/tags", response_model=TagList)
def put_product_tags(
    product_id: UUID, body: Tags, principal: CurrentPrincipal, session: DB
) -> TagList:
    """Replace this workspace's tags on the product, including those still on products merged
    into it, which move here. Inner spaces collapse, and a tag that differs only in case from
    an earlier one is dropped."""
    live_product(session, product_id)
    unique: dict[str, str] = {}
    for tag in body.tags:
        tag = " ".join(tag.split())
        unique.setdefault(tag.casefold(), tag)
    session.execute(
        delete(ProductTag).where(
            ProductTag.workspace_id == principal.workspace_id,
            ProductTag.product_id.in_(with_merged(product_id)),
        )
    )
    if unique:
        rows = [
            {"workspace_id": principal.workspace_id, "product_id": product_id, "tag": tag}
            for tag in unique.values()
        ]
        # A concurrent PUT may have inserted one first.
        session.execute(insert(ProductTag).values(rows).on_conflict_do_nothing())
    session.commit()
    return tags_of(session, principal.workspace_id, product_id)
