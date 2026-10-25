"""The product_daily_features job: one row per product, UTC day, demand family and version."""

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from pulso_ml.features.demand import FEATURE_VERSION, daily_units, known_days, product_demand
from pulso_ml.features.repository import FAMILIES, AsOf, Feature, write


def cutoff(day: date) -> datetime:
    """Features for day d use only what was captured before d+1 00:00Z (DEC-031)."""
    return datetime.combine(day + timedelta(days=1), time(), UTC)


def compute(session: Session, day: date, version: str = FEATURE_VERSION) -> list[Feature]:
    """Each product's row per family, over the listings its decisions put on it by the cutoff
    (R-15). A product with no listing that family ever saw a level for gets no row: no source,
    not a zero."""
    as_of = AsOf(session, cutoff(day))
    members = as_of.membership()
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
            Feature(product, day, name, version, *product_demand(units, covered, listings, day))
            for product, listings in products.items()
        ]
    return sorted(features)


def run(session: Session, day: date, version: str = FEATURE_VERSION) -> int:
    """Computes and appends day's rows, returning how many were new; the caller commits."""
    return write(session, compute(session, day, version))
