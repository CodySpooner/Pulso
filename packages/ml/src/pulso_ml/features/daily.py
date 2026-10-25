"""The product_daily_features job: one row per product, UTC day, family and version."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from pulso_ml.features.demand import (
    CONFIG,
    FEATURE_VERSION,
    daily_units,
    known_days,
    product_demand,
)
from pulso_ml.features.market import Seller, gt_slope, seller_inputs
from pulso_ml.features.repository import FAMILIES, AsOf, Feature, write


def cutoff(day: date) -> datetime:
    """Features for day d use only what was captured before d+1 00:00Z (DEC-031)."""
    return datetime.combine(day + timedelta(days=1), time(), UTC)


def share(part: int, whole: int) -> Decimal:
    return (Decimal(part) / max(whole, 1)).quantize(Decimal("0.0001"), ROUND_HALF_EVEN)


def compute(session: Session, day: date, version: str = FEATURE_VERSION) -> list[Feature]:
    """Each product's row per family, over the listings its decisions put on it by the cutoff
    (R-15). A product with nothing that family reads gets no row: no source, not a zero.

    Demand families as in DEC-275; then Trend's search slope (`gt_interest`) and Saturation's
    sellers (`shp_sellers`), their inputs in `features` (DEC-311). Every row lists its source's
    missed runs over t−28..t in `gap_flags`.
    """
    as_of = AsOf(session, cutoff(day))
    members = as_of.membership()
    missed = as_of.missed_runs()

    def gap_flags(source: str) -> dict[str, list[str]]:
        start = day - timedelta(days=CONFIG.gap_days)
        days = sorted(d for d in missed.get(source, ()) if start <= d <= day)
        return {"missed_runs": [d.isoformat() for d in days]}

    features = []
    for name, family in FAMILIES.items():
        levels = as_of.levels(family)
        units = daily_units(levels, sync=family.by_store)
        covered = known_days(levels, as_of.covered(family))
        tracked = {level.listing_id for level in levels if level.quantity is not None}
        products: dict[UUID, list[int]] = defaultdict(list)
        for listing in sorted(tracked & members.keys()):
            products[members[listing]].append(listing)
        features += [
            Feature(
                product,
                day,
                name,
                version,
                *product_demand(units, covered, listings, day),
                None,
                gap_flags(family.source),
            )
            for product, listings in products.items()
        ]

    def extra(
        product: UUID, name: str, source: str, inputs: dict[str, Any], gap: bool, coverage: Decimal
    ) -> None:
        features.append(
            Feature(
                product, day, name, version, None, None, coverage, gap, inputs, gap_flags(source)
            )
        )

    # R-18 per keyword: its newest capture holding 12 complete weeks, never two stitched.
    captures, live = as_of.trends(), set(members.values())
    for product, keywords in as_of.keywords().items():
        found = [captures[k] for k in sorted(keywords & captures.keys())]
        if product not in live or not found:
            continue  # merged away, or no capture yet
        picks = [
            next(
                ((s, at) for at, points in newest_first if (s := gt_slope(points)) is not None),
                None,
            )
            for newest_first in found
        ]
        used = [pick for pick in picks if pick is not None]
        inputs = {
            "gt_slope": median(s for s, _ in used) if used else None,
            "gt_keywords": len(used),
            "gt_as_of": min(at for _, at in used).isoformat() if used else None,
        }
        coverage = share(len(used), len(found))
        extra(product, "gt_interest", "google_trends", inputs, not used, coverage)

    listings, stores = as_of.sellers()
    then = cutoff(day - timedelta(days=CONFIG.panel_days))
    panel = {store for store, seen in stores.items() if seen < then}
    sellers: dict[UUID, list[Seller]] = defaultdict(list)
    for listing, product in members.items():
        if listing in listings:
            sellers[product].append(listings[listing])
    for product, rows in sellers.items():
        level, growth = seller_inputs(rows, panel, as_of.cutoff, then)
        inputs = {"shp_sellers": level, "shp_seller_g28": growth, "panel_size": len(panel)}
        coverage = share(len(panel), len(stores))
        extra(product, "shp_sellers", "shopify_stores", inputs, growth is None, coverage)
    return sorted(features)


def run(session: Session, day: date, version: str = FEATURE_VERSION) -> int:
    """Computes and appends day's rows, returning how many were new; the caller commits."""
    return write(session, compute(session, day, version))
