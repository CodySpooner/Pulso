"""Non-demand score inputs, pure (DEC-311): R-18's gt_slope and the stable seller panel."""

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from pulso_ml.features.market import Seller, TrendPoint, gt_slope, seller_inputs

LAST = date(2026, 12, 13)  # the capture's last complete day


def capture(values: list[float], tail: list[TrendPoint] | None = None) -> list[TrendPoint]:
    """Complete daily points, oldest first, ending on LAST; `tail` adds points after it."""
    start = LAST - timedelta(days=len(values) - 1)
    points = [TrendPoint(start + timedelta(days=i), v, False) for i, v in enumerate(values)]
    return points + (tail or [])


def test_gt_slope_compares_the_last_4_complete_weeks_with_the_8_before() -> None:
    weeks = [10.0] * 56 + [21.0] * 28  # m8 = 10, m4 = 21
    assert gt_slope(capture(weeks)) == pytest.approx(math.log(22 / 11))
    assert gt_slope(capture([99.0] * 6 + weeks)) == pytest.approx(math.log(22 / 11))  # older days
    # Today's partial point would shift every week by a day and pull m4 up: it's left out.
    partial = [TrendPoint(LAST + timedelta(days=1), 100.0, True)]
    assert gt_slope(capture(weeks, partial)) == pytest.approx(math.log(22 / 11))
    assert gt_slope(capture([*weeks, 100.0])) != pytest.approx(math.log(22 / 11))


def test_gt_slope_is_none_without_12_complete_weeks() -> None:
    assert gt_slope(capture([10.0] * 83)) is None
    holed = capture([10.0] * 90)
    assert gt_slope(holed[:50] + holed[51:]) is None  # a missing day inside the 84 isn't guessed
    assert gt_slope([TrendPoint(LAST, 50.0, True)]) is None
    assert gt_slope([]) is None


def at(day: int) -> datetime:
    return datetime(2026, 12, 1, tzinfo=UTC) + timedelta(days=day)


def test_seller_growth_reads_only_the_stable_panel() -> None:
    now, then = at(28), at(0)
    listings = [
        Seller(1, at(-10), None),  # selling throughout
        Seller(2, at(5), None),  # a panel store starts selling
        Seller(3, at(-10), at(20)),  # delisted between the two ends
        Seller(4, at(28), None),  # first seen exactly at now: not yet
        Seller(5, at(10), None),
    ]
    panel = {1, 2, 3, 4, 5}
    level, growth = seller_inputs(listings, panel, now, then)
    assert (level, growth) == (3, pytest.approx(math.log(4 / 3)))  # panel 2 → 3
    # Ten newly tracked stores sell it today: the level counts them, growth can't see them.
    batch = [Seller(100 + n, at(27), None) for n in range(10)]
    assert seller_inputs(listings + batch, panel, now, then) == (13, growth)
    assert seller_inputs(listings, set(), now, then) == (3, None)  # no store tracked 28 days yet
