"""CJ catalog slice. Offline collection only until the live hook contract is complete."""

import hashlib
import json
import logging
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeInt, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingSnapshot, RawPayload, Supplier
from pulso_core.money import to_minor
from pulso_sources.cj.errors import classify_error
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    UpsertStats,
    append_observation,
)

logger = logging.getLogger(__name__)
Identifier = Annotated[str, Field(min_length=1, max_length=200)]


class Product(BaseModel):
    id: Identifier
    nameEn: Annotated[str, Field(min_length=1)]
    sellPrice: str
    listedNum: Annotated[StrictInt, Field(ge=0)] | None = None


class Group(BaseModel):
    productList: list[Product]


class Page(BaseModel):
    pageSize: Annotated[int, Field(ge=1, le=100)]
    pageNumber: Annotated[int, Field(ge=1, le=1000)]
    totalRecords: NonNegativeInt
    totalPages: NonNegativeInt
    content: list[Group]


class Record(BaseModel):
    external_id: str
    title: str
    price_min_minor: int
    price_max_minor: int
    listed_count: int | None


def parse(body: bytes) -> list[Record]:
    if error := classify_error(Response(body, 200)):
        raise error
    page = Page.model_validate(json.loads(body, parse_float=Decimal)["data"])
    records = []
    seen: set[str] = set()
    for group in page.content:
        for product in group.productList:
            amounts = product.sellPrice.split("-")
            if len(amounts) not in {1, 2}:
                raise ValueError("Invalid CJ price range")
            try:
                low, high = to_minor(amounts[0], "USD"), to_minor(amounts[-1], "USD")
            except InvalidOperation:
                raise ValueError("Invalid CJ price range") from None
            if low < 0 or high < low or product.id in seen:
                raise ValueError("Invalid CJ price range or duplicate product")
            seen.add(product.id)
            records.append(
                Record(
                    external_id=product.id,
                    title=product.nameEn,
                    price_min_minor=low,
                    price_max_minor=high,
                    listed_count=product.listedNum,
                )
            )
    return records


def plan(category_ids: Sequence[str]) -> list[Target]:
    """Bounded panels, not complete category catalogs; IDs must already be resolved."""
    if len(set(category_ids)) != len(category_ids) or any(not c.strip() for c in category_ids):
        raise ValueError("CJ categories require distinct nonempty IDs")
    return [
        Target(
            "cj_catalog_panel",
            f"{category}:{order}:{country or 'all'}",
            [
                Request(
                    params={
                        "endpoint": "/product/listV2",
                        "categoryId": category,
                        "page": page,
                        "size": 100,
                        "orderBy": order,
                        "sort": "desc",
                        **({"countryCode": country} if country else {}),
                    }
                )
                for page in range(1, pages + 1)
            ],
        )
        for category in category_ids
        for order, country, pages in [(1, None, 10), (3, None, 2), (1, "US", 3)]
    ]


def dry_run(category_count: int, *, tracked_products: int = 300, freight_quotes: int = 300) -> int:
    if category_count < 0 or not 0 <= tracked_products <= 300 or not 0 <= freight_quotes <= 300:
        raise ValueError("Invalid CJ plan size")
    points = category_count * 15 * 50 + tracked_products * 2 * 10 + freight_quotes * 10
    if points >= 20000:
        raise ValueError("CJ plan must remain below 20,000 points")
    logger.info("cj_points_projection", extra={"source": "cj", "projected_points": points})
    return points


class CJAdapter:
    parser_version = "cj-catalog-v1"
    parse = staticmethod(parse)

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise CollectorsLiveDisabled("CJ live transport is not enabled in the fixture slice")

    def upsert(
        self,
        session: Session,
        records: Sequence[Record],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        if not records:
            return UpsertStats()
        supplier = session.scalar(select(Supplier).filter_by(platform="cj", external_id="cj"))
        if supplier is None:
            supplier = Supplier(platform="cj", external_id="cj", name="CJ Dropshipping")
            session.add(supplier)
            session.flush()
        inserted = 0
        for record in records:
            listing = session.scalar(
                select(Listing).filter_by(
                    source_id=payload.source_id, external_id=record.external_id
                )
            )
            if listing is None:
                listing = Listing(
                    source_id=payload.source_id,
                    external_id=record.external_id,
                    title=record.title,
                    supplier_id=supplier.id,
                    url="https://cjdropshipping.com/",
                    first_seen_at=payload.captured_at,
                    last_seen_at=payload.captured_at,
                )
                session.add(listing)
                session.flush()
            elif payload.captured_at >= listing.last_seen_at:
                listing.title, listing.last_seen_at = record.title, payload.captured_at
            values = record.model_dump(
                include={"price_min_minor", "price_max_minor", "listed_count"}
            )
            inserted += append_observation(
                session,
                ListingSnapshot(
                    listing_id=listing.id,
                    raw_payload_id=payload.id,
                    captured_at=payload.captured_at,
                    observed_for=payload.captured_at.date(),
                    parser_version=parser_version,
                    currency="USD",
                    values_hash=hashlib.sha256(
                        json.dumps(values, sort_keys=True).encode()
                    ).hexdigest(),
                    **values,
                ),
            )
        return UpsertStats(inserted=inserted, unchanged=len(records) - inserted)
