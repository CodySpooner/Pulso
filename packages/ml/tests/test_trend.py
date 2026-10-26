import math
from dataclasses import fields, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from pulso_core.scores import CADENCE, STALE_AFTER, Explanation, Normalization, version
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION, Day, product_demand
from pulso_ml.features.repository import Feature
from pulso_ml.scores import trend
from pulso_ml.scores.trend import trend_scores

DAY = date(2026, 12, 14)
LAMPS, LIGHTING, HOME = 4636, 594, 536  # Lamps < Lighting < Home & Garden
LINEAGE = (LAMPS, LIGHTING, HOME)
LAMP = UUID(int=0)  # the vault's sunset projection lamp
AS_OF = "2026-12-14T06:10:00+00:00"
FLAGS: dict[str, list[str]] = {"missed_runs": []}


def demand(product: UUID, g7: float | None, family: str = "shp_inv", gap: bool = False) -> Feature:
    v7 = None if g7 is None else 10
    return Feature(product, DAY, family, FEATURE_VERSION, v7, g7, Decimal(1), gap, None, FLAGS)


def search(product: UUID, slope: float | None, as_of: str = AS_OF) -> Feature:
    inputs = {"gt_slope": slope, "gt_keywords": int(slope is not None), "gt_as_of": as_of}
    gap = slope is None  # DEC-311 b: no slope
    return Feature(
        product, DAY, "gt_interest", FEATURE_VERSION, None, None, Decimal(1), gap, inputs, FLAGS
    )


def placed(median: float, mad: float, own: float) -> list[float]:
    """41 values with exactly this median and MAD, `own` first: the vault's Lamps (n = 41)."""
    rest = [median] + [median - mad / 2] * 10 + [median + mad / 2] * 9 + [median + mad]
    return [own, *rest, *[median - 2 * mad] * 10, *[median + 2 * mad] * 9]


def lamps() -> dict[str, Any]:
    """The worked example (illustrative): the lamp's G7 0.368, acceleration 0.268 and search
    slope ln(47/32) against Lamps' medians 0.02, 0 and 0.05 and MADs 0.12, 0.15 and 0.20;
    Saturation 73.3; no ads source. Returns trend_scores' inputs as keywords."""
    g7s = placed(0.02, 0.12, 0.368)
    accs = placed(0.0, 0.15, 0.268)
    slopes = placed(0.05, 0.20, math.log(47 / 32))
    products = [UUID(int=i) for i in range(41)]
    return dict(
        rows=[demand(p, g) for p, g in zip(products, g7s, strict=True)]
        + [search(p, s) for p, s in zip(products, slopes, strict=True)],
        week_ago=[demand(p, g - a) for p, g, a in zip(products, g7s, accs, strict=True)],
        categories=dict.fromkeys(products, LINEAGE),
        primary=dict.fromkeys(products, "shp_inv"),
        saturation={LAMP: 73.3},
        as_of=cutoff(DAY),
    )


def rounded(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {k: rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rounded(v) for v in value]
    return value


def points(explanation: Explanation) -> list[float]:
    return [50 / 3 * (c.contribution or 0) for c in explanation.components]


def test_the_vault_lamp_scores_68_6_with_its_explanation() -> None:
    score = trend_scores(**lamps())[LAMP]
    assert score.value is not None and round(score.value, 1) == 68.6
    assert score.reason is None and score.explanation is not None
    assert [round(p, 1) for p in points(score.explanation)] == [15.3, 4.7, 5.5, 0]
    assert round(50 + sum(points(score.explanation)), 1) == 75.6  # before the penalty
    lamps_ = {"category_id": LAMPS, "n": 41}
    common = {"as_of": None, "missing": False, "gap": False, "ai_derived": False, "stale": False}
    feature_row = {"as_of": "2026-12-15T00:00:00Z", "freshness": 1.0}  # the day's cutoff
    common |= {"freshness": None, "freshness_reason": None}
    assert rounded(score.explanation.model_dump(mode="json")) == {
        "model_version": trend.VERSION,
        "config_digest": version(trend.CONFIG)[1],
        "components": [
            {"name": "shp_inv_g7", "family": "shp_inv", "source": "shopify_stores",
             "weight": 0.4, "weight_eff": 0.471, "raw": 0.368, "z": 1.956,
             "normalization": lamps_, "contribution": 0.92, **common, **feature_row,
             "prompt_version": None},
            {"name": "shp_inv_acc", "family": "shp_inv", "source": "shopify_stores",
             "weight": 0.2, "weight_eff": 0.235, "raw": 0.268, "z": 1.205,
             "normalization": lamps_, "contribution": 0.284, **common, **feature_row,
             "prompt_version": None},
            {"name": "gt_slope", "family": "gt_interest", "source": "google_trends",
             "weight": 0.25, "weight_eff": 0.294, "raw": 0.384, "z": 1.128,
             "normalization": lamps_, "contribution": 0.332, **common,
             "as_of": "2026-12-14T06:10:00Z", "freshness": 1.0, "prompt_version": None},
            {"name": "ads_growth", "family": "ads", "source": None,
             "weight": 0.15, "weight_eff": 0.0, "raw": None, "z": None,
             "normalization": None, "contribution": None, **common, "missing": True,
             "prompt_version": None},
        ],
        "missing": ["ads_growth"],
        "coverage": 0.85,
        "panel_size": None,
        "penalties": [
            {"name": "saturation", "source": "shopify_stores", "raw": 73.3, "points": 6.99,
             "missing": False},
        ],
        "reason": None,
        "pending": None,
        "confidence": 0.85,  # every present input fresh: coverage
        "cautions": [],
    }  # fmt: skip
    assert Explanation.model_validate(score.explanation.model_dump(mode="json")) == (
        score.explanation
    )


def test_missing_ads_renormalise_and_are_listed_as_no_source_yet() -> None:
    explanation = trend_scores(**lamps())[LAMP].explanation
    assert explanation is not None
    g7, acc, slope, ads = explanation.components
    assert [g7.weight_eff, acc.weight_eff, slope.weight_eff] == pytest.approx(
        [0.40 / 0.85, 0.20 / 0.85, 0.25 / 0.85]
    )
    assert (ads.missing, ads.source, ads.weight_eff, ads.contribution) == (True, None, 0.0, None)
    assert explanation.missing == ("ads_growth",)
    assert explanation.coverage == pytest.approx(0.85)


def test_shopify_off_scores_from_cj_and_trends_and_lists_saturation_missing() -> None:
    day = lamps()
    day["rows"] = [
        r._replace(family="cj_stock") if r.family == "shp_inv" else r for r in day["rows"]
    ]
    day["week_ago"] = [r._replace(family="cj_stock") for r in day["week_ago"]]
    day["primary"] = dict.fromkeys(day["primary"], "cj_stock")
    day["saturation"] = {}  # no seller rows: Saturation has no value for any product
    score = trend_scores(**day)[LAMP]
    assert score.explanation is not None
    g7, acc, _, _ = score.explanation.components
    assert (g7.name, acc.name, g7.source) == ("cj_stock_g7", "cj_stock_acc", "cj")
    assert score.explanation.missing == ("ads_growth", "saturation")
    (penalty,) = score.explanation.penalties
    assert (penalty.missing, penalty.raw, penalty.points) == (True, None, None)
    assert penalty.source == "shopify_stores"  # reads "insufficient signal", not "no source yet"
    assert score.value == pytest.approx(50 + sum(points(score.explanation)))  # no penalty
    assert round(score.value or 0, 1) == 75.6


def test_a_missing_search_slope_renormalises_onto_the_demand_family() -> None:
    day = lamps()
    day["rows"][41] = search(LAMP, None)
    explanation = trend_scores(**day)[LAMP].explanation
    assert explanation is not None
    g7, acc, slope, _ = explanation.components
    assert explanation.missing == ("gt_slope", "ads_growth")
    assert slope.source == "google_trends" and slope.raw is None and slope.weight_eff == 0
    assert [g7.weight_eff, acc.weight_eff] == pytest.approx([0.40 / 0.60, 0.20 / 0.60])
    assert explanation.coverage == pytest.approx(0.60)


def test_a_search_slope_12_days_old_halves_its_weight_in_confidence_only() -> None:
    day = lamps()
    day["rows"][41] = search(
        LAMP, math.log(47 / 32), (cutoff(DAY) - timedelta(days=12)).isoformat()
    )
    score = trend_scores(**day)[LAMP]
    assert score.explanation is not None and round(score.value or 0, 1) == 68.6
    assert [c.freshness for c in score.explanation.components] == [1.0, 1.0, 0.5, None]
    assert score.explanation.confidence == pytest.approx(0.40 + 0.20 + 0.25 * 0.5)  # 0.725
    assert score.explanation.cautions == ("stale_input",)


def test_a_search_slope_over_3_weeks_old_is_missing_and_moves_the_value() -> None:
    day = lamps()
    old = cutoff(DAY) - timedelta(days=21, seconds=1)
    day["rows"][41] = search(LAMP, math.log(47 / 32), old.isoformat())
    score = trend_scores(**day)[LAMP]
    assert score.explanation is not None
    g7, acc, slope, _ = score.explanation.components
    assert (slope.missing, slope.stale, slope.as_of, slope.contribution) == (True, True, old, None)
    assert score.explanation.missing == ("gt_slope", "ads_growth")
    assert [g7.weight_eff, acc.weight_eff] == pytest.approx([0.40 / 0.60, 0.20 / 0.60])
    assert score.explanation.coverage == score.explanation.confidence == pytest.approx(0.60)
    assert round(score.value or 0, 1) == 71.4  # 68.6 with it: the rule moves stored values
    assert trend.VERSION.startswith("001-")  # so it ships as a new model_version (DEC-354)
    # Revision 1 was cut under this rule: changing it moves stored values, so bump the revision.
    assert (CADENCE["google_trends"], STALE_AFTER) == (timedelta(weeks=1), 3.0)


def test_no_row_a_week_ago_leaves_acceleration_missing() -> None:
    day = lamps()
    day["week_ago"] = day["week_ago"][1:]
    explanation = trend_scores(**day)[LAMP].explanation
    assert explanation is not None
    assert explanation.missing == ("shp_inv_acc", "ads_growth")
    assert explanation.components[1].normalization is None


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        pytest.param({"primary": {}}, "no demand family", id="no primary family"),
        pytest.param({"primary": {LAMP: "cj_stock"}}, "no velocity growth", id="no row in it"),
        pytest.param(
            {"rows": [demand(LAMP, None), search(LAMP, 0.4)]},
            "no velocity growth",
            id="G7 still NULL: insufficient history",
        ),
        pytest.param(
            {"rows": [demand(UUID(int=i), 0.1) for i in range(41)]},
            "velocity growth doesn't vary",
            id="every product's G7 is 0.1",
        ),
    ],
)
def test_without_a_qualifying_demand_family_there_is_no_score_never_0(
    change: dict[str, Any], reason: str
) -> None:
    day = lamps()
    day.update(change)
    assert trend_scores(**day)[LAMP] == (None, None, reason)


def test_a_search_slope_alone_never_scores() -> None:
    day = lamps()
    day["rows"] = [r for r in day["rows"] if r.product_id != LAMP or r.family == "gt_interest"]
    assert trend_scores(**day)[LAMP] == (None, None, "no velocity growth")


def test_a_3_to_30_unit_jump_is_bounded_by_log_growth_and_capped_at_3() -> None:
    """The real feature rows: 1 unit, then 3, then 30 a week (test_velocity's jump)."""
    sold = {-14: 1, -13: 1, -10: 1, -7: 1, **{-i: 5 for i in range(1, 7)}}
    units = {1: {DAY + timedelta(days=i): Day(n) for i, n in sold.items()}}
    covered = {1: {DAY + timedelta(days=i) for i in range(-21, 1)}}
    now, before = (product_demand(units, covered, [1], DAY + timedelta(days=i)) for i in (0, -7))
    assert (now.velocity_7d, before.velocity_7d) == (30, 3)
    day = lamps()
    day["rows"][0] = Feature(LAMP, DAY, "shp_inv", FEATURE_VERSION, *now, None, FLAGS)
    day["week_ago"][0] = Feature(LAMP, DAY, "shp_inv", FEATURE_VERSION, *before, None, FLAGS)
    score = trend_scores(**day)[LAMP]
    assert score.explanation is not None and score.value is not None
    g7, acc, _, _ = score.explanation.components
    assert g7.raw == pytest.approx(math.log(35 / 8))  # 1.48, not +900%
    assert acc.raw == pytest.approx(math.log(35 / 8) - math.log(8 / 6))
    assert (g7.z, acc.z) == (3.0, 3.0)  # (1.48 − 0.02) / (1.4826 × 0.12) = 8.2, capped
    assert 0 <= score.value <= 100


def test_every_input_at_the_cap_scores_100_and_the_penalty_clamps_at_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    day = lamps()
    products = list(day["categories"])
    day["saturation"] = {products[1]: 100.0}
    day["rows"] = (
        [demand(LAMP, 5.0), demand(products[1], -5.0), search(LAMP, 5.0), search(products[1], -5.0)]
        + day["rows"][2:41]
        + day["rows"][43:]
    )
    day["week_ago"] = [demand(LAMP, -5.0), demand(products[1], 5.0), *day["week_ago"][2:]]
    scores = trend_scores(**day)
    assert scores[LAMP].value == pytest.approx(100.0)
    low = scores[products[1]].explanation
    assert low is not None and low.penalties[0].points == 15.0
    assert scores[products[1]].value == 0.0
    monkeypatch.setattr(trend, "CONFIG", replace(trend.CONFIG, cap=4.0))  # pre would be 116.7
    assert trend_scores(**day)[LAMP].value == 100.0


@pytest.mark.parametrize(("saturation", "points_"), [(50.0, 0.0), (20.0, 0.0), (100.0, 15.0)])
def test_saturation_at_or_below_50_costs_nothing_and_100_costs_15(
    saturation: float, points_: float
) -> None:
    day = lamps()
    day["saturation"] = {LAMP: saturation}
    score = trend_scores(**day)[LAMP]
    assert score.explanation is not None and score.value is not None
    assert score.explanation.penalties[0].points == points_
    assert score.value == pytest.approx(50 + sum(points(score.explanation)) - points_)


def test_a_one_product_category_falls_back_to_its_parent_then_global() -> None:
    day = lamps()
    solo = UUID(int=99)
    day["rows"] += [demand(solo, 0.5), search(solo, 0.2)]
    day["primary"][solo] = "shp_inv"
    day["categories"][solo] = (7, LIGHTING, HOME)  # alone in category 7
    explanation = trend_scores(**day)[solo].explanation
    assert explanation is not None
    g7, _, slope, _ = explanation.components
    assert g7.normalization == slope.normalization == Normalization(category_id=LIGHTING, n=42)
    day["categories"][solo] = (7,)  # no parent: 1 product in 7, then every product
    explanation = trend_scores(**day)[solo].explanation
    assert explanation is not None
    assert explanation.components[0].normalization == Normalization(category_id=None, n=42)


def test_a_seven_product_category_uses_its_parent() -> None:
    day = lamps()
    seven = [UUID(int=99 - i) for i in range(7)]  # Score Definitions §4: n = 7 < 30
    day["rows"] += [demand(p, 0.1 * i) for i, p in enumerate(seven)]
    day["primary"].update(dict.fromkeys(seven, "shp_inv"))
    day["categories"].update(dict.fromkeys(seven, (7, LIGHTING, HOME)))
    explanation = trend_scores(**day)[seven[0]].explanation
    assert explanation is not None
    assert explanation.components[0].normalization == Normalization(category_id=LIGHTING, n=48)


def test_mad_0_in_the_category_falls_back_to_the_parent() -> None:
    day = lamps()
    flat = [UUID(int=100 + i) for i in range(30)]  # 30 lights whose G7 is all 0.1: MAD 0
    day["rows"] += [demand(p, 0.1) for p in flat]
    day["primary"].update(dict.fromkeys(flat, "shp_inv"))
    day["categories"].update(dict.fromkeys(flat, (8, LIGHTING, HOME)))
    explanation = trend_scores(**day)[flat[0]].explanation
    assert explanation is not None
    assert explanation.components[0].normalization == Normalization(category_id=LIGHTING, n=71)


def test_a_flat_search_slope_is_missing_not_zero() -> None:
    day = lamps()
    day["rows"] = [
        search(r.product_id, 0.1) if r.family == "gt_interest" else r for r in day["rows"]
    ]
    explanation = trend_scores(**day)[LAMP].explanation
    assert explanation is not None
    assert explanation.missing == ("gt_slope", "ads_growth")
    assert explanation.components[2].raw == 0.1  # the value is known; it has no spread to read


def test_families_never_mix() -> None:
    day = lamps()
    # The lamp's primary is CJ; the other lamps' shp_inv G7 can't be its cohort.
    day["primary"][LAMP] = "cj_stock"
    day["rows"].append(demand(LAMP, 0.9, family="cj_stock"))
    assert trend_scores(**day)[LAMP] == (None, None, "velocity growth doesn't vary")


def test_a_gap_flag_marks_growth_and_acceleration() -> None:
    day = lamps()
    day["week_ago"][0] = day["week_ago"][0]._replace(has_gap=True)
    explanation = trend_scores(**day)[LAMP].explanation
    assert explanation is not None
    assert [c.gap for c in explanation.components] == [False, True, False, False]
    day["rows"][0] = day["rows"][0]._replace(has_gap=True)
    explanation = trend_scores(**day)[LAMP].explanation
    assert explanation is not None
    assert [c.gap for c in explanation.components] == [True, True, False, False]


@pytest.mark.parametrize("lineage", [LINEAGE, ()], ids=["category", "global"])
def test_only_the_products_asked_for_are_scored_and_normalised_over(
    lineage: tuple[int, ...],
) -> None:
    day = lamps()
    day["categories"] = dict.fromkeys(day["categories"], lineage)
    del day["categories"][UUID(int=40)]  # a row for a product not asked for: merged away, say
    scores = trend_scores(**day)
    assert set(scores) == set(day["categories"])
    explanation = scores[LAMP].explanation
    assert explanation is not None
    used = LAMPS if lineage else None
    assert explanation.components[0].normalization == Normalization(category_id=used, n=40)


@pytest.mark.parametrize("name", [f.name for f in fields(trend.Config)])
def test_editing_any_config_value_makes_a_new_model_version(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = getattr(trend.CONFIG, name)
    bumped: Any = value + "x" if isinstance(value, str) else value + 1
    changed = replace(trend.CONFIG, **{name: bumped})
    monkeypatch.setattr(trend, "CONFIG", changed)
    explanation = trend_scores(**lamps())[LAMP].explanation
    assert explanation is not None
    assert explanation.model_version == version(changed)[0] != trend.VERSION
