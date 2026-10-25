import math
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

import pytest

from pulso_ml.features.demand import FEATURE_VERSION, Day, Demand, product_demand
from pulso_ml.scores.velocity import CONFIG, VERSION, Measure, Velocity, family_velocity, version

T = date(2026, 10, 20)
ALL = set(range(-21, 1))  # every day G7(t−7) reads, t−21..t
# 1 unit over t−20..t−14, 3 over t−13..t−7, then 30 over t−6..t: the vault's 3 → 30 jump.
SOLD = {-14: 1, -13: 1, -10: 1, -7: 1, **{-i: 5 for i in range(1, 7)}}
UNITS = {1: {T + timedelta(days=i): Day(n) for i, n in SOLD.items()}}
G7 = math.log((30 + 5) / (3 + 5))  # 1.476, not +900%
G7_PREV = math.log((3 + 5) / (1 + 5))


def day(offset: int) -> date:
    return T + timedelta(days=offset)


def run(offsets: set[int], days_observed: int = 22) -> Velocity:
    """The real feature rows for t and t−7 over one listing covered on `offsets`, then SC-1."""
    covered = {1: {day(i) for i in offsets}}
    now, week_ago = (product_demand(UNITS, covered, [1], day(i)) for i in (0, -7))
    return family_velocity(now, week_ago, days_observed)


def gap(window: str) -> Measure:
    return Measure(None, f"gap {window}")


SHORT = Measure(None, "insufficient history")


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        (set(), Velocity(Measure(30), Measure(G7), Measure(G7 - G7_PREV), False)),
        # a gap of 3 days or less keeps the exact value, flagged (DEC-275 d)
        ({-4, -3, -2}, Velocity(Measure(30), Measure(G7), Measure(G7 - G7_PREV), True)),
        ({-12, -11, -10}, Velocity(Measure(30), Measure(G7), Measure(G7 - G7_PREV), True)),
        # 4 days, or an uncovered window end, is NULL with the window named
        ({-5, -4, -3, -2}, Velocity(gap("t-7..t"), gap("t-14..t"), gap("t-14..t"), True)),
        ({0}, Velocity(gap("t-7..t"), gap("t-14..t"), gap("t-14..t"), True)),
        ({-7}, Velocity(gap("t-7..t"), gap("t-14..t"), gap("t-14..t"), True)),
        ({-12, -11, -10, -9}, Velocity(Measure(30), gap("t-14..t"), gap("t-14..t"), True)),
        ({-14}, Velocity(Measure(30), gap("t-14..t"), gap("t-14..t"), True)),
        ({-19, -18, -17, -16}, Velocity(Measure(30), Measure(G7), gap("t-21..t-7"), True)),
        ({-21}, Velocity(Measure(30), Measure(G7), gap("t-21..t-7"), True)),
    ],
)
def test_gappy_windows_are_null_and_named_never_filled_in(
    missing: set[int], expected: Velocity
) -> None:
    assert run(ALL - missing) == expected


def test_a_product_with_no_history_is_short_not_gapped() -> None:
    assert run({0}, days_observed=1) == Velocity(SHORT, SHORT, SHORT, False)
    # 10 days: the t−7 row's V7 is NULL for want of t−14, and DEC-275 flags it; still no gap
    assert run(set(range(-9, 1)), days_observed=10) == Velocity(Measure(30), SHORT, SHORT, False)


def test_a_family_with_no_source_yet_is_null_never_zero() -> None:
    # shp_bump has no feature code, and a product without a member listing gets no row
    none = Measure(None, "no source")
    assert family_velocity(None, None, 0) == Velocity(none, none, none, False)


def test_no_row_a_week_ago_is_never_carried_from_a_neighbour() -> None:
    covered = {1: {day(i) for i in ALL}}
    now = product_demand(UNITS, covered, [1], T)
    assert family_velocity(now, None, 22) == Velocity(
        Measure(30), Measure(G7), gap("t-21..t-7"), True
    )
    assert family_velocity(now, None, 21).acc == SHORT


def row(v7: int | None, g7: float | None, has_gap: bool = False) -> Demand:
    return Demand(v7, g7, Decimal(1), has_gap)


@pytest.mark.parametrize(
    ("days", "v7", "g7", "acc"),
    [
        (7, SHORT, SHORT, SHORT),
        (8, gap("t-7..t"), SHORT, SHORT),
        (14, gap("t-7..t"), SHORT, SHORT),
        (15, gap("t-7..t"), gap("t-14..t"), gap("t-14..t")),
        (21, gap("t-7..t"), gap("t-14..t"), gap("t-14..t")),
    ],
)
def test_history_each_window_needs(days: int, v7: Measure, g7: Measure, acc: Measure) -> None:
    assert family_velocity(row(None, None, True), row(None, None, True), days)[:3] == (v7, g7, acc)


@pytest.mark.parametrize(("days", "acc"), [(21, SHORT), (22, gap("t-21..t-7"))])
def test_acceleration_needs_22_days(days: int, acc: Measure) -> None:
    assert family_velocity(row(30, G7), row(3, None, True), days).acc == acc


def test_acceleration_is_this_weeks_growth_minus_last_weeks() -> None:
    result = family_velocity(row(34, 0.368), row(22, 0.160), 60)  # the vault's lamp
    assert result.acc.value == pytest.approx(0.208, abs=1e-12)
    assert family_velocity(row(5, -0.1), row(9, 0.3), 60).acc.value == pytest.approx(-0.4)


def test_a_listing_joining_mid_window_moves_neither_growth_nor_acceleration() -> None:
    units = {**UNITS, 2: {day(-i): Day(10) for i in range(4)}}
    covered = {1: {day(i) for i in ALL}, 2: {day(i) for i in range(-3, 1)}}
    now, week_ago = (product_demand(units, covered, [1, 2], day(i)) for i in (0, -7))
    assert family_velocity(now, week_ago, 22)[1:] == run(ALL)[1:]


def test_any_rule_change_makes_a_new_version() -> None:
    assert VERSION.startswith("velocity_v0-") and len(VERSION) == len("velocity_v0-") + 8
    assert CONFIG.feature_version == FEATURE_VERSION
    assert version(replace(CONFIG, feature_version="002-000000000000")) != VERSION
    assert version(replace(CONFIG, revision=1)).startswith("velocity_v1-")
