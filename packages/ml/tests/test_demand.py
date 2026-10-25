import math
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest

from pulso_ml.features.demand import (
    Day,
    Level,
    cumulative_units,
    daily_units,
    known_days,
    parse_count,
    product_demand,
    velocity,
)

T = date(2026, 10, 20)


def day(offset: int) -> date:
    return T + timedelta(days=offset)


def level(listing: int, offset: int, quantity: int | None, **kw: int) -> Level:
    """A capture at 03:00Z on T+offset; the run is the day unless given."""
    return Level(
        listing_id=listing,
        variant_id=kw.get("variant", listing),
        vendor_id=kw.get("vendor"),
        run_id=kw.get("run", offset),
        captured_at=datetime.combine(day(offset), time(3), UTC),
        quantity=quantity,
    )


def units_of(days: dict[date, Day]) -> dict[date, int]:
    return {d: v.units for d, v in days.items() if v.units}


def test_a_restock_adds_nothing_and_variants_sum_into_the_listing() -> None:
    levels = [
        *(level(1, i, q, variant=10) for i, q in enumerate([10, 7, 20, 18])),  # 20: restock
        *(level(1, i, q, variant=11) for i, q in enumerate([5, 5, 4, 4])),
    ]
    assert units_of(daily_units(levels, sync=False)[1]) == {day(1): 3, day(2): 1, day(3): 2}


def test_an_unknown_level_breaks_the_chain() -> None:
    levels = [level(1, 0, 9), level(1, 1, None), level(1, 2, 4), level(1, 3, 1)]
    assert units_of(daily_units(levels, sync=False)[1]) == {day(3): 3}


def test_a_day_ending_on_an_unknown_level_is_not_covered() -> None:
    levels = [level(1, 0, 9, variant=1), level(1, 0, 5, variant=2), level(1, 2, None, variant=2)]
    levels += [level(1, 5, 4, variant=2)]  # unchanged on days 1, 3, 4 and 6: no snapshot
    covered = {1: {day(i) for i in range(7)}}
    assert known_days(levels, covered) == {1: {day(0), day(1), day(5), day(6)}}


def test_a_negative_cumulative_delta_is_zero_and_flagged() -> None:
    assert cumulative_units("120", "118") == (0, frozenset({"negative_delta"}))
    assert cumulative_units("118", "130") == (12, frozenset())


def test_a_rounded_count_below_its_step_is_unknown() -> None:
    assert parse_count("1.2K") == (1200, 100)
    assert parse_count("15K") == (15000, 1000)
    assert parse_count("2.25M+") == (2_250_000, 10_000)
    assert parse_count("1,234") == (1234, 1)
    assert cumulative_units("1.2K", "1.2K") == (None, frozenset({"below_precision"}))
    assert cumulative_units("1.2K", "1.25K") == (None, frozenset({"below_precision"}))
    assert cumulative_units("1.2K", "1.4K") == (200, frozenset())
    with pytest.raises(ValueError):
        parse_count("lots")


def test_an_implausible_single_drop_is_excluded_and_flagged() -> None:
    quantities = [1000 - 2 * i for i in range(31)]  # 2 a day: a 28-day median of 2
    quantities += [quantities[-1] - 400, quantities[-1] - 400 - 25]
    days = daily_units([level(1, i, q) for i, q in enumerate(quantities)], sync=False)[1]
    assert days[day(31)] == Day(0, frozenset({"implausible_drop"}))
    assert days[day(32)] == Day(25)  # under 30 units: plausible whatever the median
    assert days[day(30)] == Day(2)


def test_a_store_wide_drop_in_one_crawl_is_a_sync() -> None:
    store = [level(n, 0, 100, vendor=7) for n in range(1, 6)]
    store += [level(n, 1, 97, vendor=7) for n in range(1, 6)]  # 5 of 5 in one crawl
    store += [level(n, 2, 95, vendor=7) for n in range(1, 3)]  # 2 of 5: real sales
    store += [level(n, 3, 94, vendor=7) for n in range(1, 4)]  # 3 of 5 is 60%, not above it
    days = daily_units(store, sync=True)
    assert days[1][day(1)] == Day(0, frozenset({"sync"}))
    assert units_of(days[1]) == {day(2): 2, day(3): 1}
    assert units_of(days[3]) == {day(3): 3}
    assert units_of(daily_units(store, sync=False)[1]) == {day(1): 3, day(2): 2, day(3): 1}


def covered(*offsets: range | int) -> set[date]:
    return {day(i) for r in offsets for i in (r if isinstance(r, range) else [r])}


ONE_A_DAY = {1: {day(-i): Day(1) for i in range(30)}}


def test_v7_sums_the_seven_days_after_the_baseline() -> None:
    assert velocity(ONE_A_DAY, {1: covered(range(-7, 1))}, [1], T) == 7


def test_unchanged_and_304_days_stay_covered() -> None:
    units = {1: {day(-6): Day(4)}}  # six covered days with no new snapshot
    assert velocity(units, {1: covered(range(-7, 1))}, [1], T) == 4


def test_v7_tolerates_three_missing_days_but_not_four() -> None:
    three = covered(range(-7, -4), range(-1, 1))
    assert velocity(ONE_A_DAY, {1: three}, [1], T) == 7
    assert product_demand(ONE_A_DAY, {1: three}, [1], T).has_gap
    four = covered(range(-7, -5), range(-1, 1))
    assert velocity(ONE_A_DAY, {1: four}, [1], T) is None
    demand = product_demand(ONE_A_DAY, {1: four}, [1], T)
    assert (demand.velocity_7d, demand.growth_7d, demand.has_gap) == (None, None, True)


def test_v7_needs_both_window_ends() -> None:
    assert velocity(ONE_A_DAY, {1: covered(range(-6, 1))}, [1], T) is None  # no baseline
    assert velocity(ONE_A_DAY, {1: covered(range(-7, 0))}, [1], T) is None  # nothing today


def test_g7_is_the_log_ratio_with_a_prior_of_five() -> None:
    units = {1: {day(-i): Day(3 if i < 7 else 1) for i in range(14)}}
    demand = product_demand(units, {1: covered(range(-14, 1))}, [1], T)
    assert demand.velocity_7d == 21
    assert demand.growth_7d == pytest.approx(math.log(26 / 12), abs=1e-12)
    assert (demand.coverage, demand.has_gap) == (Decimal(1), False)


def test_a_listing_added_mid_window_does_not_change_g7() -> None:
    units = {1: {day(-i): Day(3 if i < 7 else 1) for i in range(14)}}
    alone = product_demand(units, {1: covered(range(-14, 1))}, [1], T)
    units[2] = {day(-i): Day(10) for i in range(4)}
    both = product_demand(units, {1: covered(range(-14, 1)), 2: covered(range(-3, 1))}, [1, 2], T)
    assert both.growth_7d == alone.growth_7d
    assert both.velocity_7d == 21  # the newcomer has no baseline yet
    assert (both.coverage, both.has_gap) == (Decimal("0.75"), False)  # 12 of 16 listing-days
