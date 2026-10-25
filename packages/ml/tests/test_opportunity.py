from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from pulso_core.landed_cost import Amount, Inputs, landed_cost
from pulso_core.models import WorkspaceSettings
from pulso_ml.scores import opportunity as op
from pulso_ml.scores.opportunity import Margin, Stored, margin_of, opportunity

AT = datetime(2026, 12, 15, tzinfo=UTC)
# The note's worked example: the sunset lamp under workspace defaults, duty not set.
LAMP = Inputs(
    price_minor=2999,
    unit_cost=Amount(740, "USD"),
    freight=Amount(410, "USD"),
    duty_bps=None,
    payment_fee_bps=290,
    payment_fee_fixed_minor=30,
    returns_bps=500,
)


def settings(inputs: Inputs) -> WorkspaceSettings:
    return WorkspaceSettings(
        payment_fee_bps=inputs.payment_fee_bps,
        payment_fee_fixed_minor=inputs.payment_fee_fixed_minor,
        shopify_fee_bps=inputs.shopify_fee_bps,
        returns_bps=inputs.returns_bps,
    )


def row(inputs: Inputs) -> dict[str, Any]:
    """landed_cost() of the inputs as a workspace_product_economics row reads it."""
    return asdict(landed_cost(inputs)) | {"as_of": AT}


def test_the_worked_example_to_the_cent() -> None:
    withheld = landed_cost(LAMP)
    assert (withheld.missing, withheld.margin_minor) == (("duty_not_set",), None)  # R-16
    undutied = landed_cost(replace(LAMP, duty_bps=0))
    assert (undutied.landed_cost_minor, undutied.payment_fee_minor) == (1150, 117)
    assert (undutied.returns_minor, undutied.margin_minor, undutied.margin_bps) == (150, 1582, 5275)
    margin = margin_of(row(LAMP), settings(LAMP))
    assert margin == Margin(5275, True, AT)

    found = opportunity(Stored(68.6, AT), Stored(73.3, AT), margin)
    assert found.value == 65.7  # before forecasts: Momentum is Trend 68.6, Beta
    explanation = found.explanation
    assert [c.name for c in explanation.components] == ["trend", "margin", "saturation", "risk"]
    assert [c.z for c in explanation.components[:3]] == pytest.approx(
        [68.6, 87.917, 26.7], abs=1e-3
    )
    assert explanation.components[1].raw == 0.5275
    assert explanation.missing == ("risk",)
    assert explanation.coverage == pytest.approx(0.9)
    assert (explanation.confidence, explanation.cautions) == (0.7, ("duty_not_set",))
    assert explanation.model_version == op.VERSION
    points = sum(c.contribution or 0 for c in explanation.components)
    assert round(points, 1) == 65.7  # the waterfall adds up
    # The note's published p14 = 0.62 line: the same arithmetic with Momentum 62.0.
    assert opportunity(Stored(62.0, AT), Stored(73.3, AT), margin).value == 62.8


def test_a_missing_input_renormalises_and_says_which() -> None:
    no_settings = opportunity(Stored(68.6, AT), Stored(73.3, AT), None)
    assert no_settings.value == 54.6  # (0.4 × 68.6 + 0.2 × 26.7) / 0.6
    assert no_settings.explanation.missing == ("margin", "risk")
    margin = no_settings.explanation.components[1]
    assert (margin.source, margin.weight_eff, margin.contribution) == (None, 0.0, None)
    assert no_settings.explanation.confidence == pytest.approx(0.6)

    incomplete = opportunity(Stored(68.6, AT), Stored(73.3, AT), Margin(None, False, None))
    assert incomplete.value == 54.6
    assert incomplete.explanation.components[1].source == op.VIEW  # insufficient signal

    null_trend = opportunity(Stored(None, AT), None, Margin(5275, False, AT))
    assert null_trend.value == 87.9  # margin alone
    trend, _, saturation, _ = null_trend.explanation.components
    assert (trend.missing, trend.source) == (True, "trend")  # a NULL row: insufficient signal
    assert (saturation.missing, saturation.source) == (True, None)  # no row: no source yet
    assert null_trend.explanation.missing == ("trend", "saturation", "risk")


def test_nothing_present_is_no_value_never_zero() -> None:
    found = opportunity(None, None, None)
    assert (found.value, found.as_of) == (None, None)
    assert found.explanation.reason == "no trend, margin or saturation yet"
    assert found.explanation.confidence == 0.0


def test_a_margin_under_the_floor_caps_opportunity_at_25() -> None:
    capped = opportunity(Stored(90.0, AT), Stored(10.0, AT), Margin(2500, False, AT))
    assert capped.value == 25.0  # uncapped (36 + 12.5 + 18) / 0.9 = 73.9
    (penalty,) = capped.explanation.penalties
    assert (penalty.name, penalty.raw) == ("margin_floor", 0.25)
    assert penalty.points == pytest.approx(73.889 - 25, abs=1e-3)
    assert capped.explanation.reason == "margin below your floor"

    loss = opportunity(Stored(90.0, AT), None, Margin(-1200, False, AT))
    assert loss.explanation.components[1].z == 0.0  # clamped, never negative points
    assert loss.value == 25.0

    low = opportunity(Stored(5.0, AT), None, Margin(2999, False, AT))
    assert low.value == pytest.approx(round((0.4 * 5 + 0.3 * 49.983) / 0.7, 1))  # 24.3
    assert low.explanation.penalties[0].points == 0.0
    assert low.explanation.reason == "margin below your floor"

    at_floor = opportunity(Stored(90.0, AT), None, Margin(3000, False, AT))
    assert at_floor.value == round((0.4 * 90 + 0.3 * 50) / 0.7, 1)
    assert (at_floor.explanation.penalties, at_floor.explanation.reason) == ((), None)


def test_duty_not_set_lowers_confidence_but_not_the_value() -> None:
    unset = opportunity(Stored(68.6, AT), Stored(73.3, AT), Margin(5275, True, AT))
    duty = opportunity(Stored(68.6, AT), Stored(73.3, AT), Margin(5275, False, AT))
    assert unset.value == duty.value == 65.7
    assert (duty.explanation.confidence, duty.explanation.cautions) == (0.9, ())
    assert unset.explanation.confidence == pytest.approx(duty.explanation.confidence - 0.2)


def test_as_of_is_the_oldest_present_input() -> None:
    old = AT - timedelta(days=3)
    found = opportunity(
        Stored(68.6, AT), Stored(None, old - timedelta(days=9)), Margin(5275, False, old)
    )
    assert found.as_of == old  # the NULL saturation row is not an input


@pytest.mark.parametrize(
    ("unit", "freight"),
    [
        (Amount(5000, "CNY", Decimal("7.1234")), Amount(410, "USD")),
        (Amount(1180, "JPY", Decimal("151.37")), Amount(612, "JPY", Decimal("151.37"))),
        (Amount(2265, "KWD", Decimal("0.3071")), Amount(1250, "KWD", Decimal("0.3071"))),
    ],
)
def test_the_view_lines_at_duty_0_are_the_loaders_inputs_at_duty_0(
    unit: Amount, freight: Amount
) -> None:
    """margin_of() re-costs the row's USD lines; the loader would re-cost the original amounts."""
    inputs = replace(
        LAMP, unit_cost=unit, freight=freight, customs_fee_minor=95, shopify_fee_bps=50
    )
    expected = landed_cost(replace(inputs, duty_bps=0)).margin_bps
    assert expected is not None
    assert margin_of(row(inputs), settings(inputs)) == Margin(expected, True, AT)


def test_only_a_duty_gap_is_costed_at_duty_0() -> None:
    complete = replace(LAMP, duty_bps=0)
    assert margin_of(row(complete), settings(complete)) == Margin(5275, False, AT)
    two_gaps = replace(LAMP, freight=None)
    assert margin_of(row(two_gaps), settings(two_gaps)) == Margin(None, False, AT)
    assert margin_of(None, None) is None
