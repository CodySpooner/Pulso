"""Demand-family maths (vault Intelligence/Velocity & Acceleration, DEC-275): pure, no tables."""

import hashlib
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from statistics import median
from typing import NamedTuple


@dataclass(frozen=True)
class Config:
    revision: int = 2  # bump with any change to the maths below or in market.py
    k: int = 5  # G7's prior count (DEC-040)
    max_gap_days: int = 3  # a longer target-coverage gap can hide a restock
    # Guesses from the vault, tuned in Phase 4 once two weeks of data exist.
    implausible_units: int = 30
    implausible_ratio: int = 10  # × the listing's trailing median daily units
    median_days: int = 28
    sync_share: float = 0.6  # more of a store's listings dropping in one crawl is a sync
    sync_min_listings: int = 5
    # Non-demand inputs (market.py, DEC-311).
    gt_weeks: tuple[int, int] = (4, 8)  # R-18: the last 4 complete weeks against the 8 before
    panel_days: int = 28  # seller growth reads stores tracked since t−28 (M15)
    gap_days: int = 28  # gap_flags list the missed runs over t−28..t


CONFIG = Config()
_digest = hashlib.sha256(json.dumps(asdict(CONFIG), sort_keys=True).encode()).hexdigest()
# Sorts by revision, so Discover's "newest feature_version" holds (DEC-239 c).
FEATURE_VERSION = f"{CONFIG.revision:03d}-{_digest[:12]}"


@dataclass(frozen=True)
class Level:
    """One variant's stock level as one capture saw it; None when the level is unknown."""

    listing_id: int
    variant_id: int
    vendor_id: int | None  # the store, for the sync rule
    run_id: int
    captured_at: datetime
    quantity: int | None


@dataclass(frozen=True)
class Day:
    units: int
    flags: frozenset[str] = field(default=frozenset())


class Demand(NamedTuple):
    velocity_7d: int | None
    growth_7d: float | None
    coverage: Decimal
    has_gap: bool


def daily_units(levels: Iterable[Level], *, sync: bool) -> dict[int, dict[date, Day]]:
    """Units per listing per UTC day: its variants' drops between consecutive captures.

    A rise is a restock and adds 0; an unknown level breaks the chain. Drops in a store-wide
    crawl (`sync`) and implausible single drops are excluded and flagged (Demand Signals rule 6).
    """
    drops: dict[tuple[int, datetime], int] = defaultdict(int)  # (listing, capture) → units
    crawls: dict[tuple[int, int], set[tuple[int, datetime]]] = defaultdict(set)  # (store, run)
    first: dict[int, datetime] = {}
    vendors: dict[int, int | None] = {}
    last: dict[int, int | None] = {}
    for lv in sorted(levels, key=lambda lv: (lv.variant_id, lv.captured_at)):
        first[lv.listing_id] = min(first.get(lv.listing_id, lv.captured_at), lv.captured_at)
        vendors[lv.listing_id] = lv.vendor_id
        before, last[lv.variant_id] = last.get(lv.variant_id), lv.quantity
        if before is not None and lv.quantity is not None and before > lv.quantity:
            drops[lv.listing_id, lv.captured_at] += before - lv.quantity
            if lv.vendor_id is not None:
                crawls[lv.vendor_id, lv.run_id].add((lv.listing_id, lv.captured_at))

    flagged: dict[tuple[int, datetime], str] = {}
    if sync:
        for (vendor, _), keys in crawls.items():
            at = max(captured for _, captured in keys)
            tracked = sum(v == vendor and first[n] <= at for n, v in vendors.items())
            dropped = len({listing for listing, _ in keys})
            if tracked >= CONFIG.sync_min_listings and dropped > CONFIG.sync_share * tracked:
                flagged |= dict.fromkeys(keys, "sync")

    days: dict[int, dict[date, Day]] = defaultdict(dict)
    for (listing, captured), units in sorted(drops.items()):
        today, history = captured.astimezone(UTC).date(), days[listing]
        flag = flagged.get((listing, captured))
        trailing = median(
            history[d].units if d in history else 0
            for d in (today - timedelta(days=i) for i in range(1, CONFIG.median_days + 1))
        )
        if flag is None and units > CONFIG.implausible_units:
            if units > CONFIG.implausible_ratio * trailing:
                flag = "implausible_drop"
        so_far = history.get(today, Day(0))
        history[today] = (
            Day(so_far.units + units, so_far.flags)
            if flag is None
            else Day(so_far.units, so_far.flags | {flag})
        )
    return days


def known_days(levels: Iterable[Level], covered: Mapping[int, set[date]]) -> dict[int, set[date]]:
    """The covered days that ended with every variant's level known: a vanished level isn't 0."""
    captures: dict[int, list[tuple[datetime, int, bool]]] = defaultdict(list)
    for lv in levels:
        captures[lv.listing_id].append((lv.captured_at, lv.variant_id, lv.quantity is not None))
    known: dict[int, set[date]] = {}
    for listing, days in covered.items():
        events, state, i = sorted(captures.get(listing, [])), {}, 0
        known[listing] = set()
        for day in sorted(days):
            while i < len(events) and events[i][0].astimezone(UTC).date() <= day:
                state[events[i][1]] = events[i][2]
                i += 1
            if state and all(state.values()):
                known[listing].add(day)
    return known


ROUNDED = re.compile(r"(\d+(?:\.\d+)?)([KM]?)\+?", re.IGNORECASE)


def parse_count(raw: str) -> tuple[int, int]:
    """A displayed count and its rounding step: '1.2K' → (1200, 100)."""
    match = ROUNDED.fullmatch(raw.strip().replace(",", ""))
    if match is None:
        raise ValueError(f"unreadable count {raw!r}")
    number, scale = Decimal(match[1]), {"": 1, "K": 1000, "M": 10**6}[match[2].upper()]
    exponent = number.as_tuple().exponent
    assert isinstance(exponent, int)  # finite: the pattern allows digits only
    return int(number * scale), int(scale * Decimal(10) ** exponent)


def cumulative_units(previous: str, current: str) -> tuple[int | None, frozenset[str]]:
    """C(d) − C(d−1) for cumulative counts (none collected yet; vendor TikTok later)."""
    (before, step_before), (now, step_now) = parse_count(previous), parse_count(current)
    if now < before:
        return 0, frozenset({"negative_delta"})  # counts net of returns
    if now - before < max(step_before, step_now):
        return None, frozenset({"below_precision"})
    return now - before, frozenset()


def velocity(
    units: Mapping[int, Mapping[date, Day]],
    covered: Mapping[int, set[date]],
    listings: Sequence[int],
    t: date,
) -> int | None:
    """V7: units over t−6..t, from a covered baseline t−7 to a covered t; None past tolerance."""
    if not listings:
        return None
    total = 0
    for listing in listings:
        seen, gap = covered.get(listing, set()), 0
        for i in range(8):
            gap = 0 if t - timedelta(days=i) in seen else gap + 1
            if gap > CONFIG.max_gap_days:
                return None
        if t not in seen or t - timedelta(days=7) not in seen:
            return None
        days = units.get(listing, {})
        total += sum(days[d].units for d in (t - timedelta(days=i) for i in range(7)) if d in days)
    return total


def product_demand(
    units: Mapping[int, Mapping[date, Day]],
    covered: Mapping[int, set[date]],
    listings: Sequence[int],
    t: date,
) -> Demand:
    """One product's family row for day t over its member listings.

    Stable sets (vault M8): V7 reads listings covered at t−7 and t, and G7 compares both weeks
    over listings covered at t−14 and t, so a listing joining mid-window can't fake growth.
    """
    span = [t - timedelta(days=i) for i in range(8)]

    def stable(since: int) -> list[int]:
        return [n for n in listings if {t, t - timedelta(days=since)} <= covered.get(n, set())]

    v7 = velocity(units, covered, stable(7), t)
    now = velocity(units, covered, stable(14), t)
    before = velocity(units, covered, stable(14), t - timedelta(days=7))
    growth = None
    if now is not None and before is not None:
        growth = math.log((now + CONFIG.k) / (before + CONFIG.k))
    seen = sum(d in covered.get(n, set()) for n in listings for d in span)
    coverage = (Decimal(seen) / (8 * len(listings))).quantize(Decimal("0.0001"), ROUND_HALF_EVEN)
    gap = v7 is None or any(d not in covered.get(n, set()) for n in stable(7) for d in span)
    return Demand(v7, growth, coverage, gap)
