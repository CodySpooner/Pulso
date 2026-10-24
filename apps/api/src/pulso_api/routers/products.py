"""Product resources (UX-3). Products are global market data: auth applies, no workspace filter."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import Row, select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.schemas.provenance import NoSource, Sourced, Stat
from pulso_core.models import Category, Image, Listing, ListingSnapshot, Product, Source

router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
NO_PRICE = "No USD retail price observed yet."


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


def stat(
    row: Row[Any] | None, value: Callable[[Row[Any]], int], reason: str, now: datetime
) -> Stat:
    """The value from `row`, a listing's latest snapshot, with that snapshot's provenance."""
    if row is None:
        return NoSource(value=None, reason=reason)
    interval = row.config.get("expected_interval")  # seconds; without one a source is never stale
    return Sourced(
        value=value(row),
        source=row.key,
        source_name=row.name,
        as_of=row.captured_at,
        raw_payload_id=row.raw_payload_id,
        stale=isinstance(interval, int) and now - row.captured_at > timedelta(seconds=2 * interval),
    )


@router.get(
    "/{product_id}",
    response_model=ProductHeader,
    responses={308: {"description": "Merged: the survivor's URL, query string kept."}},
)
def get_product(
    product_id: UUID, request: Request, session: Annotated[Session, Depends(get_db)]
) -> Response | ProductHeader:
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:
        # Relative, so it resolves under the web app's /api rewrite too. A chained merge
        # redirects again.
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"{product.merged_into_id}{query}", status_code=308)
    # The latest snapshot of each live listing: the observations every header stat comes from.
    rows = session.execute(
        select(
            Listing.store_id,
            Listing.supplier_id,
            ListingSnapshot.captured_at,
            ListingSnapshot.raw_payload_id,
            ListingSnapshot.price_min_minor,
            ListingSnapshot.price_max_minor,
            ListingSnapshot.currency,
            Source.key,
            Source.name,
            Source.config,
        )
        .join(Listing, Listing.id == ListingSnapshot.listing_id)
        .join(Source, Source.id == Listing.source_id)
        .where(Listing.product_id == product.id, Listing.delisted_at.is_(None))
        .order_by(
            ListingSnapshot.listing_id,
            ListingSnapshot.captured_at.desc(),
            ListingSnapshot.id.desc(),
        )
        .distinct(ListingSnapshot.listing_id)
    ).all()
    now = datetime.now(UTC)
    stores = [row for row in rows if row.store_id is not None]
    suppliers = [row for row in rows if row.supplier_id is not None]
    # ponytail: USD-listed stores only (US market, owner decision 3); others wait for an FX basis.
    priced = [row for row in stores if row.currency == "USD" and row.price_min_minor is not None]

    def newest(group: list[Row[Any]]) -> Row[Any] | None:
        return max(group, key=lambda row: row.captured_at, default=None)

    def low(row: Row[Any]) -> int:
        return int(row.price_min_minor)

    def high(row: Row[Any]) -> int:
        return int(row.price_max_minor if row.price_max_minor is not None else row.price_min_minor)

    return ProductHeader(
        id=product.id,
        title=product.name,
        image_url=session.scalar(select(Image.url).where(Image.id == product.main_image_id)),
        category=session.scalar(select(Category.path).where(Category.id == product.category_id)),
        first_seen_at=product.first_seen_at,
        currency="USD",
        store_count=stat(
            newest(stores),
            lambda _: len({row.store_id for row in stores}),
            "No store listing matched yet.",
            now,
        ),
        supplier_count=stat(
            newest(suppliers),
            lambda _: len({row.supplier_id for row in suppliers}),
            "No supplier listing matched yet.",
            now,
        ),
        price_min_minor=stat(min(priced, key=low, default=None), low, NO_PRICE, now),
        price_max_minor=stat(max(priced, key=high, default=None), high, NO_PRICE, now),
    )
