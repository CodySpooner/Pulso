"""The feature store's one door to tables: reads bounded by an as-of cutoff, and the writer."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRunTarget,
    Listing,
    ListingVariant,
    ProductDailyFeature,
    RawPayload,
    Source,
    Store,
    VariantSnapshot,
)
from pulso_ml.features.demand import Level
from pulso_ml.matching.decisions import membership


@dataclass(frozen=True)
class Family:
    source: str
    scope: str  # the collector_run_targets scope that proves a listing was observed (R-06)
    captures: ColumnElement[bool]  # the raw payloads whose snapshots carry the stock level
    # Shopify listings belong to a store: its target is the store, and a store-wide drop is a sync.
    by_store: bool


# The source writers' own capture predicates (DEC-120); pulso_ml doesn't import pulso_sources.
FAMILIES = {
    "shp_inv": Family(
        "shopify_stores",
        "shopify_variants_js",
        RawPayload.request["path"].as_string().like("/products/%.js"),
        by_store=True,
    ),
    "cj_stock": Family(
        "cj",
        "cj_tracked",
        RawPayload.request["endpoint"].as_string() == "/product/stock/getInventoryByPid",
        by_store=False,
    ),
}


class Feature(NamedTuple):
    """One product_daily_features row."""

    product_id: UUID
    feature_date: date
    family: str
    feature_version: str
    velocity_7d: int | None
    growth_7d: float | None
    coverage: Decimal
    has_gap: bool


class AsOf:
    """What was known before `cutoff`: captures, target evidence and match decisions (DEC-031).

    Never reads listings.product_id or merged_into_id (today's state) or observed_for.
    """

    def __init__(self, session: Session, cutoff: datetime) -> None:
        self.session, self.cutoff = session, cutoff

    def membership(self) -> dict[int, UUID]:
        return membership(self.session, self.cutoff)

    def levels(self, family: Family) -> list[Level]:
        """Every stock capture's levels; a re-parse of a capture supersedes the older parse.

        ponytail: reads the family's whole history per day; bound it if backfills get slow.
        """
        snap = VariantSnapshot
        rows = self.session.execute(
            select(
                ListingVariant.listing_id,
                snap.variant_id,
                Listing.store_id,
                RawPayload.run_id,
                snap.captured_at,
                snap.inventory_quantity,
                snap.inventory_management,
                snap.inventory_policy,
            )
            .join(ListingVariant, ListingVariant.id == snap.variant_id)
            .join(Listing, Listing.id == ListingVariant.listing_id)
            .join(Source, Source.id == Listing.source_id)
            .join(RawPayload, RawPayload.id == snap.raw_payload_id)
            .where(Source.key == family.source, family.captures, snap.captured_at < self.cutoff)
            .order_by(snap.variant_id, snap.raw_payload_id, snap.id.desc())
            .distinct(snap.variant_id, snap.raw_payload_id)
        )
        # A Shopify level means stock only when Shopify tracks it and won't oversell (Demand
        # Signals family 1).
        return [
            Level(
                r.listing_id,
                r.variant_id,
                r.store_id,
                r.run_id,
                r.captured_at,
                r.inventory_quantity
                if not family.by_store
                or (r.inventory_management, r.inventory_policy) == ("shopify", "deny")
                else None,
            )
            for r in rows
        ]

    def covered(self, family: Family) -> dict[int, set[date]]:
        """The UTC days each listing's target succeeded, by its capture's time; unchanged and
        304 answers count (R-06).

        ponytail: Shopify's target is the whole store, so a listing outside that day's .js
        panel reads as covered; per-listing evidence if shp_inv ever runs again (DEC-261).
        """
        target = CollectorRunTarget
        query = (
            select(Listing.id, RawPayload.captured_at)
            .select_from(target)
            .join(RawPayload, RawPayload.id == target.raw_payload_id)
        )
        if family.by_store:
            query = query.join(Store, Store.domain == target.target_id).join(
                Listing, Listing.store_id == Store.id
            )
        else:
            query = query.join(Listing, Listing.external_id == target.target_id)
        rows = self.session.execute(
            query.join(Source, Source.id == Listing.source_id).where(
                Source.key == family.source,
                target.scope == family.scope,
                target.status == "success",
                RawPayload.captured_at < self.cutoff,
            )
        )
        days: dict[int, set[date]] = defaultdict(set)
        for listing_id, captured_at in rows:
            days[listing_id].add(captured_at.astimezone(UTC).date())
        return days


def write(session: Session, rows: Sequence[Feature]) -> int:
    """Appends rows; a key already written keeps its row untouched (append-only history)."""
    if not rows:
        return 0
    statement = (
        insert(ProductDailyFeature)
        .on_conflict_do_nothing()
        .returning(ProductDailyFeature.product_id)
    )
    return len(session.scalars(statement, [row._asdict() for row in rows]).all())
