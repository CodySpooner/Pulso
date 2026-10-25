"""The feature store's one door to tables: reads bounded by an as-of cutoff, and the writer."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectionGap,
    CollectorRunTarget,
    Listing,
    ListingVariant,
    ProductDailyFeature,
    ProductKeyword,
    RawPayload,
    SearchTrend,
    Source,
    Store,
    VariantSnapshot,
)
from pulso_ml.features.demand import Level
from pulso_ml.features.market import Seller, TrendPoint
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
    features: dict[str, Any] | None  # a non-demand family's inputs (DEC-311)
    gap_flags: dict[str, list[str]]


class AsOf:
    """What was known before `cutoff`: captures, target evidence and match decisions (DEC-031),
    and the gaps, keywords and sightings the gap audit, workspaces and crawls had recorded.

    Never reads listings.product_id or merged_into_id (today's state) or observed_for.
    listings.delisted_at is a time, judged against each cutoff in `market.live()`.
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

    def missed_runs(self) -> dict[str, set[date]]:
        """Each source's UTC days that a missed slot touches, as the gap audit had recorded them
        by the cutoff: Data Health's gap days. A fill doesn't clear one: fills are Data Health's
        display state, never feature coverage (DEC-060 D4)."""
        rows = self.session.execute(
            select(Source.key, CollectionGap.slot_start, CollectionGap.slot_end)
            .join(Source, Source.id == CollectionGap.source_id)
            .where(CollectionGap.detected_at < self.cutoff)
        )
        days: dict[str, set[date]] = defaultdict(set)
        for key, start, end in rows:
            day, last = (
                at.astimezone(UTC).date() for at in (start, end - timedelta(microseconds=1))
            )
            while day <= last:
                days[key].add(day)
                day += timedelta(days=1)
        return days

    def keywords(self) -> dict[UUID, set[str]]:
        """Each product's keywords that some workspace had confirmed by the cutoff, as the weekly
        Trends set reads them (DEC-292). A later decision rewrites its row, so that keyword drops
        out of earlier days: missing, never leaked."""
        keywords: dict[UUID, set[str]] = defaultdict(set)
        for product_id, keyword in self.session.execute(
            select(ProductKeyword.product_id, ProductKeyword.keyword).where(
                ProductKeyword.status == "confirmed", ProductKeyword.decided_at < self.cutoff
            )
        ):
            keywords[product_id].add(keyword)
        return keywords

    def trends(self) -> dict[str, list[tuple[datetime, list[TrendPoint]]]]:
        """Each keyword's US Trends captures (a SerpApi answer or a CSV import), newest first,
        keyed like product_keywords (casefolded, spacing collapsed). One capture's points are
        never mixed with another's; a re-parse supersedes the older parse.

        ponytail: reads every capture's points per day; bound it if backfills get slow.
        """
        st = SearchTrend
        rows = self.session.execute(
            select(st.keyword, st.raw_payload_id, st.captured_at, st.observed_for)
            .add_columns(st.value, st.is_partial)
            .where(st.geo == "US", st.captured_at < self.cutoff)
            # A capture's rows share its captured_at, so this keeps one row per parse.
            .order_by(st.captured_at.desc(), st.raw_payload_id.desc(), st.keyword, st.observed_for)
            .order_by(st.id.desc())
            .distinct(st.captured_at, st.raw_payload_id, st.keyword, st.observed_for)
        )
        captures: dict[str, dict[int, tuple[datetime, list[TrendPoint]]]] = defaultdict(dict)
        for r in rows:
            keyword = " ".join(r.keyword.casefold().split())
            _, points = captures[keyword].setdefault(r.raw_payload_id, (r.captured_at, []))
            points.append(TrendPoint(r.observed_for, float(r.value), r.is_partial))
        return {keyword: list(found.values()) for keyword, found in captures.items()}

    def sellers(self) -> tuple[dict[int, Seller], dict[int, datetime]]:
        """Store listings Pulso had seen by the cutoff, and when Pulso first saw each store it
        tracked by then (DEC-247 g, h)."""
        listings = {
            listing_id: Seller(*row)
            for listing_id, *row in self.session.execute(
                select(
                    Listing.id,
                    Listing.store_id,
                    Listing.first_seen_at,
                    Listing.delisted_at,  # today's value: `live()` ignores one after its time
                ).where(Listing.store_id.is_not(None), Listing.first_seen_at < self.cutoff)
            )
        }
        stores = self.session.execute(
            select(Store.id, Store.first_seen_at).where(Store.first_seen_at < self.cutoff)
        )
        return listings, dict(stores.tuples().all())


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
