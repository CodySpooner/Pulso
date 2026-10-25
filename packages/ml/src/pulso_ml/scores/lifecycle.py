"""Lifecycle Stage (SPEC §7, vault Intelligence/Lifecycle Stage, DEC-307): pure, no tables."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Literal, NamedTuple


@dataclass(frozen=True)
class Config:
    revision: int = 0  # the `v0` in VERSION; bump with any change to the rules below
    # Working guesses (DEC-307), tuned once two weeks of data exist.
    min_days: int = 15  # G7(t) reads a covered t−14
    up: float = math.log(1.2)  # +20% week on week
    down: float = math.log(0.8)  # −20% week on week
    brake: float = -0.25  # growth fell by 0.25 or more in a week
    young_days: int = 28
    dead_units: int = 1  # per 7 days
    emerging_units: int = 3  # per 7 days


CONFIG = Config()


def version(config: Config) -> str:
    """`lifecycle_v<revision>-<hash8>` (vault Score Definitions §2): new thresholds, new version."""
    digest = hashlib.sha256(json.dumps(asdict(config), sort_keys=True).encode()).hexdigest()
    return f"lifecycle_v{config.revision}-{digest[:8]}"


VERSION = version(CONFIG)


class Stage(NamedTuple):
    name: Literal["emerging", "rising", "peaking", "declining", "dead"] | None
    reason: str  # the rule that fired, or why there is no stage


def lifecycle_stage(
    *,
    v7: int | None,
    v7_prev: int | None,
    g7: float | None,
    g7_prev: float | None,
    days_observed: int,
    has_gap: bool,
    age_days: int | None,
    delisted_all: bool,
) -> Stage:
    """One product's stage on day t from its primary demand family's feature rows (DEC-275).

    Inputs come from the rows at t and t−7: `v7` = V7(t), `v7_prev` = V7(t−7), `g7` = G7(t) and
    `g7_prev` = G7(t−7), so acceleration is `g7 − g7_prev`. G7 is the week-on-week growth
    ln((V7 + 5) / (V7 prev + 5)), so "+20%" below means G7 ≥ ln 1.2. `days_observed` counts the
    family's days up to t, t included (0: the product has no demand family). `has_gap` is either
    row's gap flag. `age_days` is days since the source's launch date (None: unknown).

    No stage, with its reason, never a guessed one:
    - no source: no demand family, delisted or not.
    - insufficient history: fewer than 15 days observed, or V7(t), V7(t−7) or G7(t) missing
      without a gap (a stable listing set still too new).
    - gap: a gap flag on either row, even when every value is present. Gaps are never filled in.

    Otherwise the first rule that holds wins:
    - dead · delisted: every listing is delisted. Checked before history: a fact, not a trend.
    - dead · no sales: at most 1 unit in each of the last two weeks.
    - declining · two weeks down: growth at or below −20% this week and last week.
    - declining · sharp drop: growth at or below −36% this week (G7 ≤ 2 ln 0.8).
    - peaking · braking: growth at or above +20%, but 0.25 or more below last week's.
    - peaking · plateau: growth under +20%: flat, a stall after a run, or one week down that isn't
      a decline yet.
    - emerging · new and growing: growth at or above +20%, launched 28 days ago or less, and at
      least 3 units this week.
    - rising · growing: growth at or above +20% otherwise.

    Until G7(t−7) exists (a product's first 21 days) "two weeks down" and "braking" can't hold.
    Hysteresis (two nights before a change shows) is the scores writer's: it keeps yesterday's.
    """
    if days_observed <= 0:
        return Stage(None, "no source")
    if delisted_all:
        return Stage("dead", "delisted")
    if days_observed < CONFIG.min_days:
        return Stage(None, "insufficient history")
    if has_gap:
        return Stage(None, "gap")
    if v7 is None or v7_prev is None or g7 is None:
        return Stage(None, "insufficient history")
    if v7 <= CONFIG.dead_units and v7_prev <= CONFIG.dead_units:
        return Stage("dead", "no sales")
    if g7 <= CONFIG.down and g7_prev is not None and g7_prev <= CONFIG.down:
        return Stage("declining", "two weeks down")
    if g7 <= 2 * CONFIG.down:
        return Stage("declining", "sharp drop")
    if g7 >= CONFIG.up and g7_prev is not None and g7 - g7_prev <= CONFIG.brake:
        return Stage("peaking", "braking")
    if g7 < CONFIG.up:
        return Stage("peaking", "plateau")
    if age_days is not None and age_days <= CONFIG.young_days and v7 >= CONFIG.emerging_units:
        return Stage("emerging", "new and growing")
    return Stage("rising", "growing")
