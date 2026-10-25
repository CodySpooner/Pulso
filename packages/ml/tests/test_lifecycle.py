import math
from dataclasses import fields, replace
from typing import Any

import pytest

from pulso_core.scores import version
from pulso_ml.scores.lifecycle import CONFIG, VERSION, Config, Stage, lifecycle_stage

UP, DOWN, BRAKE = CONFIG.up, CONFIG.down, CONFIG.brake
E = 2**-20  # a step past a boundary; exact in binary, so 0.5 − 0.75 lands on BRAKE exactly


def stage(
    *,
    v7: int | None = 34,
    v7_prev: int | None = 22,
    g7: float | None = 0.368,
    g7_prev: float | None = 0.160,
    days: int = 60,
    gap: bool = False,
    age: int | None = 70,
    delisted: bool = False,
) -> Stage:
    """The vault's sunset lamp (rising) unless overridden."""
    return lifecycle_stage(
        v7=v7,
        v7_prev=v7_prev,
        g7=g7,
        g7_prev=g7_prev,
        days_observed=days,
        has_gap=gap,
        age_days=age,
        delisted_all=delisted,
    )


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        # dead: at most 1 unit in each of the two weeks
        ({"v7": 1, "v7_prev": 1, "g7": 0.0}, ("dead", "no sales")),
        ({"v7": 2, "v7_prev": 1, "g7": math.log(7 / 6)}, ("peaking", "plateau")),
        ({"v7": 1, "v7_prev": 2, "g7": math.log(6 / 7)}, ("peaking", "plateau")),
        ({"v7": 0, "v7_prev": 0, "g7": 0.0}, ("dead", "no sales")),
        ({"v7": 0, "v7_prev": 20, "g7": math.log(5 / 25)}, ("declining", "sharp drop")),
        ({"delisted": True}, ("dead", "delisted")),
        # declining: −20% or worse two weeks running, or −36% or worse in one
        ({"g7": DOWN, "g7_prev": DOWN}, ("declining", "two weeks down")),
        ({"g7": DOWN + E, "g7_prev": DOWN}, ("peaking", "plateau")),
        ({"g7": DOWN, "g7_prev": DOWN + E}, ("peaking", "plateau")),
        ({"g7": 2 * DOWN, "g7_prev": None}, ("declining", "sharp drop")),
        ({"g7": 2 * DOWN + E, "g7_prev": None}, ("peaking", "plateau")),
        # peaking: still +20% but growth fell by 0.25 or more in a week
        ({"g7": 0.5, "g7_prev": 0.75}, ("peaking", "braking")),
        ({"g7": 0.5, "g7_prev": 0.75 - E}, ("rising", "growing")),
        ({"g7": UP, "g7_prev": UP + 1}, ("peaking", "braking")),
        (
            {"v7": 120, "v7_prev": 80, "g7": math.log(125 / 85), "g7_prev": 0.7},
            ("peaking", "braking"),
        ),
        ({"g7": 0.5, "g7_prev": None}, ("rising", "growing")),  # no acceleration yet
        # emerging: launched within 28 days, +20%, at least 3 units
        (
            {"age": 28, "v7": 3, "v7_prev": 1, "g7": math.log(8 / 6)},
            ("emerging", "new and growing"),
        ),
        ({"age": 29, "v7": 3, "v7_prev": 1, "g7": math.log(8 / 6)}, ("rising", "growing")),
        ({"age": 28, "v7": 2, "v7_prev": 0, "g7": math.log(7 / 5)}, ("rising", "growing")),
        ({"age": None, "v7": 3, "v7_prev": 1, "g7": math.log(8 / 6)}, ("rising", "growing")),
        # rising at exactly +20%; just under is a plateau
        ({"g7": UP}, ("rising", "growing")),
        ({"g7": UP - E}, ("peaking", "plateau")),
        ({}, ("rising", "growing")),
    ],
)
def test_each_boundary_from_both_sides(kw: dict[str, Any], expected: tuple[str, str]) -> None:
    assert stage(**kw) == expected


@pytest.mark.parametrize(
    ("kw", "expected"),
    [
        (
            {"v7": None, "v7_prev": None, "g7": None, "g7_prev": None, "age": None, "days": 0},
            "no source",
        ),
        ({"days": 0, "delisted": True}, "no source"),  # no demand family: no stage at all
        ({"days": 14}, "insufficient history"),
        ({"days": 10, "gap": True, "v7": None, "g7": None}, "insufficient history"),
        ({"days": 30, "v7_prev": None}, "insufficient history"),  # stable set too new for G7
        ({"days": 30, "g7": None}, "insufficient history"),
        ({"gap": True}, "gap"),  # every value present: a gap still gets no stage
        ({"gap": True, "v7": None, "g7": None}, "gap"),
    ],
)
def test_no_stage_says_why(kw: dict[str, Any], expected: str) -> None:
    assert stage(**kw) == (None, expected)


def test_fifteen_days_is_enough_history() -> None:
    assert stage(days=15, g7_prev=None) == ("rising", "growing")


def test_delisted_is_dead_whatever_the_history() -> None:
    assert stage(days=3, gap=True, v7=None, g7=None, delisted=True) == ("dead", "delisted")


def test_version_names_the_revision_and_the_config_digest() -> None:
    model_version, digest = version(Config())
    assert VERSION == model_version == f"{CONFIG.revision:03d}-{digest[:12]}"  # imp-413


@pytest.mark.parametrize("name", [f.name for f in fields(Config)])
def test_changing_any_threshold_changes_the_version(name: str) -> None:
    value = getattr(CONFIG, name)
    changed = replace(CONFIG, **{name: value + (1 if isinstance(value, int) else 0.01)})
    assert version(changed)[0] != VERSION
