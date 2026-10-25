"""The Suppliers tab (UX-6, R-16): every live supplier listing of a product, costed to the US by
the Profit tab's own calculation, with the Best margin and Fastest shipping picks (DEC-264)."""

import json
from dataclasses import fields
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import Row, select, true
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import Principal, current_principal
from pulso_api.errors import APIError
from pulso_api.routers.account import workspace_settings
from pulso_api.routers.products import DB, is_stale
from pulso_api.routers.profit import ProfitCalc, ProfitCalcRequest, calc_profit
from pulso_api.schemas.provenance import NoSource, Sourced, Stat
from pulso_core.landed_cost import LandedCost, best
from pulso_core.landed_cost_loader import in_stock
from pulso_core.models import Listing, ListingSnapshot, Product, Source, Supplier, SupplierOffer

router = APIRouter(prefix="/v1/products")
CURSOR = TypeAdapter(tuple[int, int, int])
ENGINE = {field.name for field in fields(LandedCost)}  # the calc answer's engine lines
Pick = Literal["best_margin", "fastest"]


class Rating(Sourced):
    """`value` is hundredths of a star out of 5: 470 is 4.70."""

    count: int | None  # reviews behind it, when the source gives them


class Orders(Sourced):
    semantics: Literal["lifetime", "window"]  # sold_count, or orders over `window_days`
    window_days: int | None


class BulkTier(BaseModel):
    min_quantity: int
    unit_minor: int  # in `currency`: tiers inherit the offer's currency (DEC-030)
    currency: str
    as_of: AwareDatetime  # the listing's last sighting, which refreshes its offer


class SupplierRow(BaseModel):
    listing_id: int
    title: str
    url: str  # the listing on the supplier's site
    supplier_name: str
    platform: str  # suppliers.platform, e.g. "cj"
    supplier_url: str | None
    supplier_country: str | None
    warehouse_country: str | None
    unit_cost_minor: int | None  # as the supplier lists it; `cost` holds it in USD
    currency: str | None
    cost: ProfitCalc = Field(
        description="POST /v1/profit/calc's answer for this supplier at quantity 1 (DEC-246)."
    )
    picks: list[Pick]
    in_stock: bool  # not known to be out of stock (DEC-243); out-of-stock rows never pick
    stock: Stat
    rating: Rating | NoSource
    orders: Orders | NoSource
    years_active: Stat
    moq: Stat
    bulk_tiers: list[BulkTier]
    source_name: str
    last_seen: AwareDatetime
    stale: bool
    as_of: AwareDatetime | None = Field(
        description="The latest listing snapshot (`unit_cost_minor`, stock, rating, orders); "
        "every other number carries its own trace."
    )


class Picks(BaseModel):
    best_margin: SupplierRow | None  # best() over in-stock rows: complete rows only (R-16)
    fastest: SupplierRow | None  # lowest max days to the US in stock, then lowest landed cost


class SuppliersPage(BaseModel):
    country: Literal["US"]
    rows: list[SupplierRow]
    next_cursor: str | None = Field(description="Pass as `cursor` with the same query.")
    picks: Picks  # over every row, whichever page this is
    as_of: AwareDatetime | None  # the newest time Pulso saw any of these listings


@router.get(
    "/{product_id}/suppliers",
    response_model=SuppliersPage,
    responses={308: {"description": "Merged: the survivor's suppliers, query string kept."}},
)
def get_product_suppliers(
    product_id: UUID,
    request: Request,
    session: DB,
    principal: Annotated[Principal, Depends(current_principal)],
    country: Annotated[Literal["US"], Query(description="Destination; US only in v1")] = "US",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> Response | SuppliersPage:
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:  # like the header and sellers (DEC-238)
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"../{product.merged_into_id}/suppliers{query}", status_code=308)
    after = None
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid suppliers cursor.") from None
    now = datetime.now(UTC)
    workspace_settings(session, principal)  # a first read commits the new row before any load
    snap = (
        select(
            ListingSnapshot.price_min_minor,
            ListingSnapshot.currency,
            ListingSnapshot.captured_at,
            ListingSnapshot.raw_payload_id,
            ListingSnapshot.available,
            ListingSnapshot.stock,
            ListingSnapshot.rating,
            ListingSnapshot.review_count,
            ListingSnapshot.sold_count,
            ListingSnapshot.orders_window,
            ListingSnapshot.window_days,
        )
        .where(ListingSnapshot.listing_id == Listing.id)
        .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
        .lateral()
    )
    # The loader's own set: live supplier listings of the product (landed_cost_loader.calculate).
    # ponytail: the whole set loads per request, so the picks cover every row and keyset paging
    # runs in Python, as on Sellers (DEC-247); a product has a handful of supplier listings.
    listings = session.execute(
        select(Listing, Supplier, SupplierOffer, Source, snap)
        .join(Supplier, Supplier.id == Listing.supplier_id)
        .join(Source, Source.id == Listing.source_id)
        .outerjoin(SupplierOffer, SupplierOffer.listing_id == Listing.id)
        .outerjoin(snap, true())
        .where(Listing.product_id == product.id, Listing.delisted_at.is_(None))
        .order_by(Listing.id)
    ).all()
    # ponytail: one Profit calc per listing (about ten queries each), so every row is exactly
    # what the Profit tab shows for that supplier. Batch through the loader's own loop if a
    # product ever carries dozens of supplier listings.
    rows = [
        supplier_row(
            row,
            calc_profit(
                ProfitCalcRequest(product_id=product.id, supplier_listing_id=row.Listing.id),
                principal,
                session,
            ),
            now,
        )
        for row in listings
    ]
    stocked = [row for row in rows if row.in_stock]
    # The engine's own ranking, on the engine's own lines (R-16: complete rows only).
    margin = best(
        {row.listing_id: LandedCost(**row.cost.model_dump(include=ENGINE)) for row in stocked}
    )
    fastest = min(
        (row for row in stocked if row.cost.freight_max_days is not None),
        key=lambda row: (
            row.cost.freight_max_days,
            row.cost.landed_cost_minor is None,
            row.cost.landed_cost_minor or 0,
            row.listing_id,
        ),
        default=None,
    )
    for row in rows:
        row.picks = [pick for pick, chosen in picked(margin, fastest) if chosen == row.listing_id]
    rows.sort(key=sort_key)
    shown = [row for row in rows if after is None or sort_key(row) > after]
    page = shown[:limit]
    return SuppliersPage(
        country=country,
        rows=page,
        next_cursor=json.dumps(list(sort_key(page[-1]))) if len(shown) > limit else None,
        picks=Picks(
            best_margin=next((row for row in rows if row.listing_id == margin), None),
            fastest=fastest,
        ),
        as_of=max((row.last_seen for row in rows), default=None),
    )


def picked(margin: int | None, fastest: SupplierRow | None) -> list[tuple[Pick, int | None]]:
    return [("best_margin", margin), ("fastest", fastest.listing_id if fastest else None)]


def sort_key(row: SupplierRow) -> tuple[int, int, int]:
    """Complete rows by margin, best first; then the rest by landed cost; unpriced last. Known
    out-of-stock rows follow every in-stock one in the same order (tiers 3-5), so the first row
    is the Best margin pick."""
    cost = row.cost
    out = 0 if row.in_stock else 3
    if cost.complete and cost.margin_minor is not None:
        return out, -cost.margin_minor, row.listing_id
    if cost.landed_cost_minor is not None:
        return out + 1, cost.landed_cost_minor, row.listing_id
    return out + 2, 0, row.listing_id


def supplier_row(row: Row[Any], cost: ProfitCalc, now: datetime) -> SupplierRow:
    listing: Listing = row.Listing
    supplier: Supplier = row.Supplier
    offer: SupplierOffer | None = row.SupplierOffer
    source: Source = row.Source
    seen = listing.last_seen_at

    def trace(value: int | None, as_of: datetime | None, raw: int | None, reason: str) -> Stat:
        if value is None or as_of is None:
            return NoSource(value=None, reason=reason)
        return Sourced(
            value=value,
            source=source.key,
            source_name=source.name,
            as_of=as_of,
            raw_payload_id=raw,
            stale=is_stale(source.config, as_of, now),
        )

    def observed(value: int | None, reason: str) -> Stat:
        """A number from the latest snapshot, with that snapshot's trace."""
        return trace(value, row.captured_at, row.raw_payload_id, reason)

    def entity(value: int | None, reason: str) -> Stat:
        """A supplier or offer term: no capture of its own, so the listing's last sighting."""
        return trace(value, seen, None, reason)

    stars = (
        observed(int(row.rating * 100), "")
        if row.rating is not None
        else entity(None if supplier.rating is None else int(supplier.rating * 100), "")
    )
    rating: Rating | NoSource = NoSource(value=None, reason="The source gives no rating.")
    if isinstance(stars, Sourced):
        reviews = row.review_count if row.rating is not None else None
        rating = Rating(**stars.model_dump(), count=reviews)
    window = row.window_days if row.sold_count is None else None
    sold = observed(row.sold_count if window is None else row.orders_window, "")
    orders: Orders | NoSource = NoSource(value=None, reason="The source gives no order count.")
    if isinstance(sold, Sourced):
        semantics: Literal["lifetime", "window"] = "window" if window else "lifetime"
        orders = Orders(**sold.model_dump(), semantics=semantics, window_days=window)
    terms = "No offer terms captured for this listing yet."
    return SupplierRow(
        listing_id=listing.id,
        title=listing.title,
        url=listing.url,
        supplier_name=supplier.name,
        platform=supplier.platform,
        supplier_url=supplier.url,
        supplier_country=supplier.country,
        warehouse_country=offer.warehouse_country if offer else None,
        unit_cost_minor=row.price_min_minor,
        currency=row.currency,
        cost=cost,
        picks=[],
        in_stock=in_stock(row.available, row.stock),
        stock=observed(row.stock, "The source reports no stock for this listing."),
        rating=rating,
        orders=orders,
        years_active=entity(supplier.years_active, "The source gives no years active."),
        moq=entity(offer.moq if offer else None, terms),
        bulk_tiers=tiers(offer, row.currency, seen),
        source_name=source.name,
        last_seen=seen,
        stale=is_stale(source.config, seen, now),
        as_of=row.captured_at,
    )


def tiers(offer: SupplierOffer | None, currency: str | None, seen: datetime) -> list[BulkTier]:
    """The offer's tiers that state both integers; anything else is left out, never guessed."""
    if offer is None or currency is None:
        return []
    found = []
    for tier in offer.bulk_tiers:
        quantity, unit = tier.get("min_quantity"), tier.get("unit_minor")
        if type(quantity) is int and type(unit) is int and quantity > 0 and unit >= 0:
            found.append(
                BulkTier(min_quantity=quantity, unit_minor=unit, currency=currency, as_of=seen)
            )
    return found
