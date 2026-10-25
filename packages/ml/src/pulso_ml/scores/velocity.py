"""Velocity & Acceleration per demand family (SPEC §7, vault Velocity & Acceleration, DEC-310).

Pure, no tables: reads a family's product_daily_features rows (DEC-275), never sums families.
"""

from dataclasses import dataclass
from typing import NamedTuple, Protocol

from pulso_core.scores import version
from pulso_ml.features.demand import FEATURE_VERSION


@dataclass(frozen=True)
class Config:
    revision: int = 0  # bump with any change to the rules below
    feature_version: str = FEATURE_VERSION  # the rows these rules read: new G7 maths, new version


CONFIG = Config()
VERSION, _ = version(CONFIG)  # `{revision:03d}-{hash12}` (DEC-306 d)


class Row(Protocol):
    """The product_daily_features columns read here: a `Feature`, its model or a `Demand`."""

    @property
    def velocity_7d(self) -> float | None: ...
    @property
    def growth_7d(self) -> float | None: ...
    @property
    def has_gap(self) -> bool: ...


class Measure(NamedTuple):
    value: float | None
    why: str | None = None  # a NULL's reason: "no source", "insufficient history" or "gap <window>"


class Velocity(NamedTuple):
    v7: Measure
    g7: Measure
    acc: Measure
    has_gap: bool  # a window had a gap; a value it kept is exact (tolerated), never filled in


def family_velocity(now: Row | None, week_ago: Row | None, days_observed: int) -> Velocity:
    """One product's velocity, growth and acceleration in one demand family on day t.

    `now` and `week_ago` are its rows for t and t−7 (None: no row). `days_observed` counts the
    days since its first row in the family, t included, as Lifecycle reads it (DEC-307).
    - V7(t) = units over t−6..t from a covered t−7 (DEC-275 d).
    - G7(t) = ln((V7(t) + 5) / (V7(t−7) + 5)), both weeks over the listings covered at t−14 and t.
    - Acc(t) = G7(t) − G7(t−7), from the two rows' stored G7.

    The rows already apply the gap rules (DEC-275 d): a target-coverage gap over 3 days or an
    uncovered window end stores NULL; a shorter gap keeps the exact value and sets has_gap.
    A NULL here says why:
    - no source: no row at t; the family has no series for the product (DEC-040).
    - insufficient history: fewer days than the window needs: 8 (V7), 15 (G7), 22 (Acc).
    - gap <window>: history enough but NULL; the window is t-7..t, t-14..t or t-21..t-7 (G7(t−7)).
    Nothing is interpolated or carried forward: only the rows at t and t−7 are read.
    """
    if now is None:
        none = Measure(None, "no source")
        return Velocity(none, none, none, False)

    # ponytail: an emptied stable panel (every listing replaced within 14 days) reads as a gap;
    # telling it from one needs the panel size on the row (FS-1 backlog, DEC-310 c).
    def measure(value: float | None, days: int, window: str) -> Measure:
        if value is not None:
            return Measure(value)
        return Measure(None, "insufficient history" if days_observed < days else f"gap {window}")

    v7 = measure(now.velocity_7d, 8, "t-7..t")
    g7 = measure(now.growth_7d, 15, "t-14..t")
    before = measure(week_ago.growth_7d if week_ago else None, 22, "t-21..t-7")
    acc = g7 if g7.value is None else before
    if g7.value is not None and before.value is not None:
        acc = Measure(g7.value - before.value)

    def tolerated(row: Row | None) -> bool:  # DEC-275 also flags a V7 NULL from short history
        return row is not None and row.has_gap and row.velocity_7d is not None

    gapped = any((m.why or "").startswith("gap") for m in (v7, g7, acc))
    return Velocity(v7, g7, acc, gapped or tolerated(now) or tolerated(week_ago))
