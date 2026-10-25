import math
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from pulso_core.scores import Normalization, version
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.features.market import Seller, seller_inputs
from pulso_ml.features.repository import Feature
from pulso_ml.scores import saturation
from pulso_ml.scores.saturation import band, saturation_scores

DAY = date(2026, 12, 14)
LAMPS, LIGHTING, HOME = 4636, 594, 536  # Lamps < Lighting < Home & Garden
LINEAGE = (LAMPS, LIGHTING, HOME)
LAMP = UUID(int=0)  # the vault's sunset projection lamp


def row(product: UUID, inputs: dict[str, Any] | None, missed: list[str] | None = None) -> Feature:
    gap = inputs is None or inputs["shp_seller_g28"] is None
    flags = {"missed_runs": missed or []}
    return Feature(
        product, DAY, "shp_sellers", FEATURE_VERSION, None, None, Decimal(1), gap, inputs, flags
    )


def placed(median: float, mad: float, own: float) -> list[float]:
    """41 values with exactly this median and MAD, `own` first: the vault's Lamps (n = 41)."""
    rest = [median] + [median - mad / 2] * 10 + [median + mad / 2] * 9 + [median + mad]
    return [own, *rest, *[median - 2 * mad] * 10, *[median + 2 * mad] * 9]


def lamps() -> tuple[list[Feature], dict[UUID, tuple[int, ...]]]:
    """The worked example (illustrative): the lamp's 9 stores and panel 5 → 9, against Lamps'
    median ln 4 and MAD 0.50 for the level and 0 and 0.20 for the growth. The other lamps'
    counts are placed so ln(1 + s) lands on those statistics, so most aren't whole numbers."""
    levels = placed(math.log(4), 0.50, math.log(10))
    growths = placed(0.0, 0.20, math.log(10 / 6))
    rows = [
        row(UUID(int=i), {"shp_sellers": math.expm1(s), "shp_seller_g28": g, "panel_size": 12})
        for i, (s, g) in enumerate(zip(levels, growths, strict=True))
    ]
    rows[0] = row(LAMP, {"shp_sellers": 9, "shp_seller_g28": math.log(10 / 6), "panel_size": 12})
    return rows, {r.product_id: LINEAGE for r in rows}


def test_the_vault_lamp_without_cj_scores_73_7_high() -> None:
    rows, categories = lamps()
    score = saturation_scores(rows, categories)[LAMP]
    assert score.value is not None and round(score.value, 1) == 73.7
    assert (score.band, score.reason) == ("high", None)
    explanation = score.explanation
    assert explanation is not None
    sellers, growth, ads = explanation.components
    assert (sellers.name, growth.name, ads.name) == ("shp_sellers", "shp_seller_g28", "ads_active")
    assert sellers.raw == pytest.approx(math.log(10)) and growth.raw == math.log(10 / 6)
    assert (round(sellers.z or 0, 2), round(growth.z or 0, 2)) == (1.24, 1.72)
    assert sellers.normalization == growth.normalization == Normalization(category_id=LAMPS, n=41)
    assert sellers.weight_eff == pytest.approx(0.40 / 0.65)
    assert growth.weight_eff == pytest.approx(0.25 / 0.65)
    assert (sellers.source, growth.source, ads.source) == ("shopify_stores", "shopify_stores", None)
    assert ads.missing and ads.weight_eff == 0 and ads.contribution is None and ads.z is None
    assert explanation.missing == ("ads_active",)
    assert explanation.coverage == pytest.approx(0.65 / 0.90)  # CJ listings aren't configured
    assert explanation.panel_size == 12
    assert explanation.model_version == saturation.VERSION == version(saturation.CONFIG)[0]
    points = sum(50 / 3 * (c.contribution or 0) for c in explanation.components)
    assert 50 + points == pytest.approx(score.value)


def test_missing_growth_renormalises_onto_the_seller_count() -> None:
    rows, categories = lamps()
    rows[0] = row(LAMP, {"shp_sellers": 9, "shp_seller_g28": None, "panel_size": 0})
    score = saturation_scores(rows, categories)[LAMP]
    assert score.explanation is not None
    sellers, growth, _ = score.explanation.components
    assert score.explanation.missing == ("shp_seller_g28", "ads_active")
    assert (sellers.weight_eff, growth.weight_eff, growth.raw) == (1.0, 0.0, None)
    assert growth.source == "shopify_stores"  # reads "insufficient signal", not "no source yet"
    assert score.explanation.coverage == pytest.approx(0.40 / 0.90)
    assert score.value == pytest.approx(50 + 50 * (sellers.z or 0) / 3)
    assert score.explanation.panel_size == 0


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        pytest.param([], "no seller count", id="no shp_sellers row"),
        pytest.param([row(LAMP, None)], "no seller count", id="a version-001 row: no inputs"),
        pytest.param(
            [
                row(UUID(int=i), {"shp_sellers": 3, "shp_seller_g28": 0.1, "panel_size": 4})
                for i in range(40)
            ],
            "seller counts don't vary",
            id="every product sells in 3 stores",
        ),
    ],
)
def test_without_a_usable_seller_count_there_is_no_score_never_0(
    rows: list[Feature], reason: str
) -> None:
    categories = {UUID(int=i): LINEAGE for i in range(40)}
    score = saturation_scores(rows, categories)[LAMP]
    assert score == (None, None, None, reason)


def test_only_the_products_asked_for_are_scored_and_normalised_over() -> None:
    rows, categories = lamps()
    del categories[UUID(int=40)]
    scores = saturation_scores(rows, categories)
    assert set(scores) == set(categories)
    explanation = scores[LAMP].explanation
    assert explanation is not None
    assert explanation.components[0].normalization == Normalization(category_id=LAMPS, n=40)


def test_a_missed_run_flags_the_growth_window_not_the_level() -> None:
    rows, categories = lamps()
    rows[0] = row(LAMP, rows[0].features, missed=["2026-12-01"])
    explanation = saturation_scores(rows, categories)[LAMP].explanation
    assert explanation is not None
    assert [c.gap for c in explanation.components] == [False, True, False]


# The phase verify line: 31 lamps and 8 stores tracked for months (the panel). Store 7 picked up
# every lamp 10 days ago, store 6 every third. Ten stores first seen yesterday list lamp 30, the
# most crowded.
NOW, THEN = cutoff(DAY), cutoff(DAY - timedelta(days=28))
OLD, RECENT, NEW = NOW - timedelta(days=90), NOW - timedelta(days=10), NOW - timedelta(days=1)
CROWDED = UUID(int=30)


def tracked(new_stores: int) -> list[Feature]:
    stores = {s: OLD for s in range(8)} | {100 + k: NEW for k in range(new_stores)}
    panel = {s for s, seen in stores.items() if seen < THEN}
    rows = []
    for i in range(31):
        listings = [Seller(s, OLD, None) for s in range(i % 4 + 1)] + [Seller(7, RECENT, None)]
        if i % 3 == 0:
            listings.append(Seller(6, RECENT, None))
        if UUID(int=i) == CROWDED:
            listings = [Seller(s, OLD, None) for s in range(8)]
            listings += [Seller(100 + k, NEW, None) for k in range(new_stores)]
        level, growth = seller_inputs(listings, panel, NOW, THEN)
        row_ = row(
            UUID(int=i), {"shp_sellers": level, "shp_seller_g28": growth, "panel_size": len(panel)}
        )
        rows.append(row_)
    return rows


def test_ten_newly_tracked_stores_leave_untouched_products_unchanged() -> None:
    categories = {UUID(int=i): LINEAGE for i in range(31)}
    before = saturation_scores(tracked(0), categories)
    after = saturation_scores(tracked(10), categories)
    untouched = set(categories) - {CROWDED}
    assert {p: before[p] for p in untouched} == {p: after[p] for p in untouched}
    old, new = before[CROWDED].explanation, after[CROWDED].explanation
    assert old is not None and new is not None
    assert old.components[0].raw == pytest.approx(math.log(9))
    assert new.components[0].raw == pytest.approx(math.log(19))
    assert old.components[1] == new.components[1]  # growth: the new stores aren't in the panel
    assert old.panel_size == new.panel_size == 8


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "low"),
        (34.99, "low"),
        (35, "medium"),
        (50, "medium"),
        (65, "medium"),
        (65.01, "high"),
        (100, "high"),
    ],
)
def test_bands_low_below_35_high_above_65(value: float, expected: str) -> None:
    assert band(value) == expected


def test_the_value_is_clamped_to_0_100(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(saturation, "CONFIG", replace(saturation.CONFIG, cap=6.0, shp_sellers=0.01))
    rows, categories = lamps()
    rows[0] = row(LAMP, {"shp_sellers": 1e9, "shp_seller_g28": 9.0, "panel_size": 12})
    rows[1] = row(UUID(int=1), {"shp_sellers": 0, "shp_seller_g28": -9.0, "panel_size": 12})
    scores = saturation_scores(rows, categories)
    assert (scores[LAMP].value, scores[UUID(int=1)].value) == (100, 0)


@pytest.mark.parametrize(
    "change",
    [
        {"shp_sellers": 0.5},
        {"ads_active": 0.0},
        {"min_n": 20},
        {"high_above": 70.0},
        {"revision": 1},
    ],
)
def test_a_config_change_changes_the_model_version(
    monkeypatch: pytest.MonkeyPatch, change: dict[str, Any]
) -> None:
    monkeypatch.setattr(saturation, "CONFIG", replace(saturation.CONFIG, **change))
    rows, categories = lamps()
    explanation = saturation_scores(rows, categories)[LAMP].explanation
    assert explanation is not None
    assert explanation.model_version == version(saturation.CONFIG)[0] != saturation.VERSION
