"""Non-demand score inputs (DEC-311): Trend's search slope (R-18) and Saturation's sellers.

Pure, like demand.py: the repository hands them one capture, or one product's store listings.
"""

import math
from collections.abc import Iterable, Sequence
from datetime import date, datetime, timedelta
from typing import NamedTuple

from pulso_ml.features.demand import CONFIG


class TrendPoint(NamedTuple):
    observed_for: date
    value: float
    is_partial: bool


class Seller(NamedTuple):
    """A store listing: when Pulso first saw it, and when a complete crawl delisted it."""

    store_id: int
    first_seen_at: datetime
    delisted_at: datetime | None


def gt_slope(capture: Iterable[TrendPoint]) -> float | None:
    """ln((m4 + 1) / (m8 + 1)) inside one capture: m4 is the mean of the last 4 complete weeks
    and m8 of the 8 before. Partial points go first; weeks are 7-day blocks counted back from the
    last complete day, so a day missing among those 84 gives None, never a guess."""
    points = {p.observed_for: p.value for p in capture if not p.is_partial}
    if not points:
        return None
    recent, base = (7 * weeks for weeks in CONFIG.gt_weeks)
    days = [max(points) - timedelta(days=i) for i in range(recent + base)]
    if any(d not in points for d in days):
        return None
    m4 = sum(points[d] for d in days[:recent]) / recent
    m8 = sum(points[d] for d in days[recent:]) / base
    return math.log((m4 + 1) / (m8 + 1))


def live(seller: Seller, at: datetime) -> bool:
    """Listed at `at`: seen before it and not delisted before it (the Sellers tab's rule)."""
    return seller.first_seen_at < at and (seller.delisted_at is None or seller.delisted_at >= at)


def seller_inputs(
    listings: Sequence[Seller], panel: set[int], now: datetime, then: datetime
) -> tuple[int, float | None]:
    """Stores selling the product at `now`, counting every tracked store ("9 stores sell this"
    holds whenever they were added), and ln((p_now + 1) / (p_then + 1)) over the stable panel
    alone, so a batch of newly tracked stores never reads as market growth (M15). None with no
    panel yet."""

    def selling(at: datetime) -> set[int]:
        return {s.store_id for s in listings if live(s, at)}

    level = selling(now)
    if not panel:
        return len(level), None
    return len(level), math.log((len(level & panel) + 1) / (len(selling(then) & panel) + 1))
