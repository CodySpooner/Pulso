"""Manual CJ costs/freight through the shared template; inventory remains unknown."""

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel, PositiveInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import (
    Listing,
    ListingVariant,
    RawPayload,
    ShippingOption,
    SupplierOffer,
    VariantSnapshot,
)
from pulso_core.money import to_minor
from pulso_sources.cj import CJAdapter, Record
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    UpsertStats,
    Writer,
    append_observation,
)

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData

# DEC-156: manual prices are their own writer, read explicitly; detail keeps the default read.
CSV_WRITER = Writer(RawPayload.request["mode"].as_string() == "csv", ("price_minor",))


class Row(BaseModel):
    cj_product_id: str | None = None
    sku: str | None = None
    name: str
    unit_cost: Decimal
    currency: str
    warehouse_country: str | None = None
    ship_cost_us: Decimal | None = None
    min_days: int | None = None
    max_days: int | None = None
    moq: PositiveInt | None = None
    observed_for: date | None = None


class ImportAdapter:
    parser_version = "cj-csv-v1"

    def __init__(self, data: ImportData) -> None:
        if data.csv is None:
            raise ValueError("CJ imports require the shared CSV template")
        self.rows = data.csv.rows

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise CollectorsLiveDisabled("CJ CSV is offline only")

    def parse(self, body: bytes) -> Sequence[Row]:
        return [Row.model_validate(row) for row in self.rows]

    def upsert(
        self, session: Session, records: Sequence[Row], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        products = {row.sku: row.cj_product_id for row in records if row.sku and row.cj_product_id}
        groups: dict[str, list[Row]] = defaultdict(list)
        for row in records:
            groups[row.cj_product_id or products.get(row.sku or "") or f"csv-sku:{row.sku}"].append(
                row
            )
        inserted = unchanged = 0
        for external_id, rows in groups.items():
            first = rows[0]
            costs = [to_minor(row.unit_cost, row.currency) for row in rows]
            evidence = dict(
                raw_payload_id=payload.id,
                captured_at=payload.captured_at,
                observed_for=first.observed_for or payload.captured_at.date(),
                parser_version=parser_version,
            )
            stats = CJAdapter().upsert(
                session,
                [
                    Record(
                        external_id=external_id,
                        title=first.name,
                        price_min_minor=min(costs),
                        price_max_minor=max(costs),
                        listed_count=None,
                        currency=first.currency,
                        observed_for=first.observed_for,
                    )
                ],
                payload,
                parser_version=parser_version,
            )
            inserted += stats.inserted
            unchanged += stats.unchanged
            listing = session.scalars(
                select(Listing).filter_by(source_id=payload.source_id, external_id=external_id)
            ).one()
            if payload.captured_at >= listing.last_seen_at:
                offer = session.get(SupplierOffer, listing.id)
                if offer is None:
                    offer = SupplierOffer(listing_id=listing.id)
                    session.add(offer)
                # DEC-186: an omitted column or blank cell is no evidence and keeps the stored
                # value; a new offer keeps the schema defaults (moq 1, no warehouse).
                moqs = {row.moq for row in rows if row.moq is not None}
                if moqs:
                    offer.moq = max(moqs)  # DEC-074 already rejects two stated MOQs
                countries = {row.warehouse_country for row in rows if row.warehouse_country}
                if countries:
                    offer.warehouse_country = countries.pop() if len(countries) == 1 else None
            for row, cost in zip(rows, costs, strict=True):
                variant = None
                if row.sku:
                    matches = session.scalars(
                        select(ListingVariant).filter_by(listing_id=listing.id, sku=row.sku)
                    ).all()
                    # An ambiguous SKU falls back to the unique manual identity (P1-47 C-M3).
                    variant = (
                        matches[0]
                        if len(matches) == 1
                        else session.scalar(
                            select(ListingVariant).filter_by(
                                listing_id=listing.id, external_id=f"csv-sku:{row.sku}"
                            )
                        )
                    )
                    if variant is None:
                        variant = ListingVariant(
                            listing_id=listing.id,
                            external_id=f"csv-sku:{row.sku}",
                            sku=row.sku,
                            first_seen_at=payload.captured_at,
                            last_seen_at=payload.captured_at,
                        )
                        session.add(variant)
                        session.flush()
                    values = {"price_minor": cost, "currency": row.currency}
                    added = append_observation(
                        session,
                        VariantSnapshot(
                            variant_id=variant.id,
                            **values,
                            **evidence,
                            values_hash=hashlib.sha256(
                                json.dumps(values, sort_keys=True).encode()
                            ).hexdigest(),
                        ),
                        writer=CSV_WRITER,
                    )
                    inserted += added
                    unchanged += not added
                if row.ship_cost_us is not None:
                    added = append_observation(
                        session,
                        ShippingOption(
                            listing_id=listing.id,
                            variant_id=variant.id if variant else None,
                            origin_country=row.warehouse_country,
                            destination_country="US",
                            quantity=1,
                            method="manual",
                            cost_minor=to_minor(row.ship_cost_us, row.currency),
                            currency=row.currency,
                            min_days=row.min_days,
                            max_days=row.max_days,
                            **evidence,
                        ),
                    )
                    inserted += added
                    unchanged += not added
        return UpsertStats(inserted=inserted, unchanged=unchanged)
