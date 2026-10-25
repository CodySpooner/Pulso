"""Google Merchant Center Popular products: the owner's weekly CSV download only (DEC-267).

Google's terms allow internal use only, so no public page may show these rows.
"""

import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import AmazonRank, Listing, ListingVariant, PopularProduct, RawPayload
from pulso_core.money import to_minor
from pulso_ml.matching.gtin import gtin14
from pulso_ml.matching.matcher import canonical, redirects
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response, UpsertStats

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData


class Row(BaseModel):
    report_week: date
    country: str
    category: str | None = None
    popularity_rank: int
    previous_rank: int | None = None
    title: str
    brand: str | None = None
    availability: str | None = None
    relative_demand: str | None = None
    relative_demand_change: str | None = None
    gtins: str | None = None
    price_range_min: Decimal | None = None
    price_range_max: Decimal | None = None
    price_range_currency: str | None = None


class ImportAdapter:
    parser_version = "merchant-csv-v1"

    def __init__(self, data: ImportData) -> None:
        if data.csv is None:
            raise ValueError("Popular products imports use the CSV template")
        self.rows = data.csv.rows

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise CollectorsLiveDisabled("Merchant Center Popular products is CSV only")

    def parse(self, body: bytes) -> Sequence[Row]:
        return [Row.model_validate(row) for row in self.rows]

    def upsert(
        self, session: Session, records: Sequence[Row], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        if not records:
            return UpsertStats()

        def minor(amount: Decimal | None, currency: str | None) -> int | None:
            # A price without its currency is unknown, never assumed to be USD.
            return to_minor(amount, currency) if amount is not None and currency else None

        # One statement per 1,000 rows: a weekly download holds about 16,000 (DEC-267 b).
        ids = session.scalars(
            insert(PopularProduct)
            .on_conflict_do_nothing(
                index_elements=[
                    *PopularProduct.observation_keys,
                    "raw_payload_id",
                    "parser_version",
                ]
            )
            .returning(PopularProduct.id),
            [
                {
                    "source_id": payload.source_id,
                    "country": row.country,
                    "category": row.category,
                    "rank": row.popularity_rank,
                    "previous_rank": row.previous_rank,
                    "title": row.title,
                    "brand": row.brand,
                    "availability": row.availability,
                    "relative_demand": row.relative_demand,
                    "relative_demand_change": row.relative_demand_change,
                    "gtins": row.gtins,
                    "price_min_minor": minor(row.price_range_min, row.price_range_currency),
                    "price_max_minor": minor(row.price_range_max, row.price_range_currency),
                    "currency": row.price_range_currency,
                    "observed_for": row.report_week,
                    "captured_at": payload.captured_at,
                    "raw_payload_id": payload.id,
                    "parser_version": parser_version,
                }
                for row in records
            ],
        ).all()
        return UpsertStats(inserted=len(ids), unchanged=len(records) - len(ids))


def gtin_tokens(gtins: str | None) -> list[str]:
    """A row's GTINs as Google wrote them: space-separated (BigQuery), or by comma or semicolon."""
    return [token for token in re.split(r"[\s,;]+", gtins or "") if token]


def link_products(
    session: Session, rows: Sequence[PopularProduct | AmazonRank]
) -> dict[int, UUID | None]:
    """Each row's one live product sharing a valid GTIN, read now and never stored (DEC-267 c).

    M-4's gtin14 normalises both sides and merges are followed to the live product.
    No product, or GTINs on two products, leaves the row unlinked: it still shows.
    ponytail: reads every barcode per call, like M-4's pass; a normalised column when it grows.
    """
    merged = redirects(session)
    products: defaultdict[str, set[UUID | None]] = defaultdict(set)
    for barcode, product_id in session.execute(
        select(ListingVariant.barcode, Listing.product_id)
        .join(Listing, Listing.id == ListingVariant.listing_id)
        .where(ListingVariant.barcode.is_not(None), Listing.product_id.is_not(None))
    ).tuples():
        if (code := gtin14(barcode)) is not None:
            products[code].add(canonical(merged, product_id))
    linked: dict[int, UUID | None] = {}
    for row in rows:
        codes = {gtin14(token) for token in gtin_tokens(row.gtins)} - {None}
        found = set().union(*(products.get(code, set()) for code in codes if code))
        linked[row.id] = found.pop() if len(found) == 1 else None
    return linked
