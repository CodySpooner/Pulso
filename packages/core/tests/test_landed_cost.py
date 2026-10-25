from dataclasses import replace
from decimal import Decimal

import pytest

from pulso_core.landed_cost import MISSING, Amount, Inputs, best, bps_of, landed_cost
from pulso_core.landed_cost_loader import cheapest

# The Profit note's worked example: $29.99, CJ $6.20, freight $4.85, duty 20%, 2.9% + $0.30, 5%.
EXAMPLE = Inputs(
    price_minor=2999,
    unit_cost=Amount(620, "USD"),
    freight=Amount(485, "USD"),
    duty_bps=2000,
    payment_fee_bps=290,
    payment_fee_fixed_minor=30,
    returns_bps=500,
)


def test_worked_example_to_the_cent() -> None:
    cost = landed_cost(EXAMPLE)
    assert (cost.goods_minor, cost.freight_minor, cost.duty_minor, cost.customs_fee_minor) == (
        620,
        485,
        124,
        0,
    )
    assert cost.landed_cost_minor == 1229
    assert cost.payment_fee_minor == 117  # 86.971 -> 87, plus 30
    assert cost.returns_minor == 150  # 149.95 -> 150
    assert cost.margin_minor == 1503  # break-even CPA $15.03
    assert cost.margin_bps == 5012  # 1503 / 2999 = 50.117%
    assert (cost.complete, cost.missing, cost.estimates) == (True, (), ())


def test_lines_sum_to_the_totals() -> None:
    cost = landed_cost(replace(EXAMPLE, shopify_fee_bps=200, customs_fee_minor=150))
    lines = [cost.goods_minor, cost.freight_minor, cost.duty_minor, cost.customs_fee_minor]
    fees = [cost.payment_fee_minor, cost.shopify_fee_minor, cost.returns_minor]
    assert None not in lines + fees
    assert cost.landed_cost_minor == sum(line or 0 for line in lines)
    assert cost.margin_minor == 2999 - sum(line or 0 for line in lines + fees)


def test_payment_and_shopify_fees_are_on_the_price() -> None:
    cost = landed_cost(replace(EXAMPLE, shopify_fee_bps=200, payment_fee_fixed_minor=0))
    assert cost.payment_fee_minor == 87
    assert cost.shopify_fee_minor == 60  # 2% of 29.99 = 59.98
    assert cost.margin_minor == 1503 + 30 - 60


def test_customs_fee_is_per_order_not_per_unit() -> None:
    one = landed_cost(replace(EXAMPLE, customs_fee_minor=250))
    three = landed_cost(replace(EXAMPLE, customs_fee_minor=250, quantity=3))
    assert one.customs_fee_minor == three.customs_fee_minor == 250
    assert one.landed_cost_minor == 1229 + 250
    assert three.goods_minor == 3 * 620
    assert three.landed_cost_minor == 1860 + 485 + 372 + 250  # duty 20% of 18.60


def test_duty_not_set_is_incomplete_and_has_no_margin() -> None:
    cost = landed_cost(replace(EXAMPLE, duty_bps=None))
    assert cost.duty_minor is None
    assert (cost.complete, cost.missing) == (False, ("duty_not_set",))
    assert (cost.landed_cost_minor, cost.margin_minor, cost.margin_bps) == (None, None, None)
    # The other lines still show, so the UI can say what is known.
    assert (cost.goods_minor, cost.freight_minor, cost.returns_minor) == (620, 485, 150)


def test_duty_zero_is_set_not_missing() -> None:
    cost = landed_cost(replace(EXAMPLE, duty_bps=0))
    assert (cost.duty_minor, cost.complete, cost.margin_minor) == (0, True, 1503 + 124)


def test_ddp_zeroes_duty_and_customs_fee() -> None:
    cost = landed_cost(replace(EXAMPLE, duty_bps=None, customs_fee_minor=250, ddp=True))
    assert (cost.duty_minor, cost.customs_fee_minor) == (0, 0)
    assert (cost.complete, cost.missing) == (True, ())
    assert cost.margin_minor == 1503 + 124


def test_duty_can_pass_100_percent() -> None:
    assert landed_cost(replace(EXAMPLE, duty_bps=14500)).duty_minor == 899  # 145% of 6.20


def test_returns_are_a_share_of_revenue() -> None:
    assert landed_cost(replace(EXAMPLE, returns_bps=0)).returns_minor == 0
    assert landed_cost(replace(EXAMPLE, returns_bps=1000)).returns_minor == 300  # 299.9
    assert landed_cost(replace(EXAMPLE, returns_bps=10000)).returns_minor == 2999


@pytest.mark.parametrize(
    "bps,expected",
    [(5, 0), (15, 2), (25, 2), (35, 4), (45, 4), (46, 5)],  # 0.5 -> 0, 1.5 -> 2, 2.5 -> 2 ...
)
def test_half_cents_round_half_even(bps: int, expected: int) -> None:
    cost = landed_cost(replace(EXAMPLE, price_minor=1000, returns_bps=bps))
    assert cost.returns_minor == expected


@pytest.mark.parametrize(
    "unit_cost,quantity,expected",
    [
        (Amount(1000, "JPY", Decimal("150")), 1, 667),  # 6.666... USD
        (Amount(1000, "JPY", Decimal("150")), 3, 2000),  # 20.00 exactly, never 3 x 6.67
        (Amount(1234, "KWD", Decimal("0.30")), 1, 411),  # 1.234 KWD = 4.1133 USD
        (Amount(620, "USD"), 1, 620),
        (Amount(4, "CNY", Decimal("8")), 1, 0),  # 0.5 cent -> 0
        (Amount(12, "CNY", Decimal("8")), 1, 2),  # 1.5 cents -> 2
    ],
)
def test_fx_uses_currency_exponents_and_rounds_once(
    unit_cost: Amount, quantity: int, expected: int
) -> None:
    cost = landed_cost(replace(EXAMPLE, unit_cost=unit_cost, quantity=quantity))
    assert cost.goods_minor == expected


def test_freight_converts_at_its_own_rate() -> None:
    cost = landed_cost(replace(EXAMPLE, freight=Amount(3600, "CNY", Decimal("7.2"))))
    assert cost.freight_minor == 500


def test_fx_missing_withholds_the_line_and_totals() -> None:
    cost = landed_cost(replace(EXAMPLE, unit_cost=Amount(4500, "CNY"), freight=Amount(100, "EUR")))
    assert (cost.goods_minor, cost.freight_minor, cost.duty_minor) == (None, None, None)
    assert cost.missing == ("fx_missing",)  # once, though both lines lack a rate
    assert (cost.landed_cost_minor, cost.margin_minor) == (None, None)


def test_missing_inputs_are_named() -> None:
    cost = landed_cost(
        replace(EXAMPLE, price_minor=None, unit_cost=None, freight=None, duty_bps=None)
    )
    assert cost.missing == (
        "price_missing",
        "supplier_cost_missing",
        "freight_missing",
        "duty_not_set",
    )
    assert (cost.payment_fee_minor, cost.shopify_fee_minor, cost.returns_minor) == (None,) * 3


def test_freight_gap_carries_the_loaders_reason() -> None:
    cost = landed_cost(replace(EXAMPLE, freight=None, freight_gap="freight_variant_mismatch"))
    assert cost.missing == ("freight_variant_mismatch",)


def test_landed_cost_shows_without_a_price() -> None:
    cost = landed_cost(replace(EXAMPLE, price_minor=None))
    assert (cost.landed_cost_minor, cost.margin_minor, cost.missing) == (
        1229,
        None,
        ("price_missing",),
    )


def test_a_loss_has_a_negative_margin() -> None:
    cost = landed_cost(replace(EXAMPLE, price_minor=1000))
    assert cost.margin_minor == 1000 - 1229 - (29 + 30) - 50
    assert cost.margin_bps == -3380


def test_owner_estimates_count_as_complete_and_are_listed() -> None:
    cost = landed_cost(replace(EXAMPLE, estimates=("returns_bps", "duty_bps")))
    assert cost.complete
    assert cost.estimates == ("duty_bps", "returns_bps")


def test_a_price_must_be_positive() -> None:
    with pytest.raises(ValueError):
        landed_cost(replace(EXAMPLE, price_minor=0))


def test_an_unquoted_cheap_supplier_cannot_be_best() -> None:
    cheap = landed_cost(replace(EXAMPLE, unit_cost=Amount(100, "USD"), freight=None))
    quoted = landed_cost(EXAMPLE)
    dearer = landed_cost(replace(EXAMPLE, unit_cost=Amount(700, "USD")))
    assert best({1: cheap, 2: dearer, 3: quoted}) == 3
    assert best({1: cheap}) is None
    loss = landed_cost(replace(EXAMPLE, price_minor=1000))  # complete, but loses money
    assert best({1: cheap, 2: loss}) == 2


BIG = 2**62  # x 2 is 2^63, one past BIGINT


@pytest.mark.parametrize(
    "unit_cost", [Amount(BIG, "USD"), Amount(BIG, "JPY", Decimal("150"))], ids=["USD", "JPY"]
)
def test_a_line_past_bigint_is_named_not_returned(unit_cost: Amount) -> None:
    cost = landed_cost(replace(EXAMPLE, unit_cost=unit_cost, quantity=2))
    assert (cost.goods_minor, cost.duty_minor, cost.landed_cost_minor) == (None, None, None)
    assert (cost.complete, cost.missing, cost.margin_minor) == (
        False,
        ("amount_out_of_range",),
        None,
    )


def test_fees_and_totals_past_bigint_are_named_not_returned() -> None:
    top = 2**63 - 1  # every input is inside the request bounds
    fees = landed_cost(
        replace(EXAMPLE, price_minor=top, payment_fee_bps=10000, payment_fee_fixed_minor=top)
    )
    assert (fees.payment_fee_minor, fees.margin_minor, fees.margin_bps) == (None, None, None)
    assert (fees.missing, fees.returns_minor) == (("amount_out_of_range",), bps_of(top, 500))
    duty = landed_cost(replace(EXAMPLE, unit_cost=Amount(BIG, "USD"), duty_bps=20000))
    assert (duty.goods_minor, duty.duty_minor, duty.landed_cost_minor) == (BIG, None, None)
    landed = landed_cost(replace(EXAMPLE, unit_cost=Amount(top, "USD"), duty_bps=0))
    assert (landed.goods_minor, landed.landed_cost_minor) == (top, None)
    ratio = landed_cost(replace(EXAMPLE, price_minor=1, unit_cost=Amount(BIG, "USD"), duty_bps=0))
    assert ratio.landed_cost_minor == BIG + 485  # margin_bps would be ~ -4.6e22
    assert (ratio.margin_minor, ratio.margin_bps, ratio.complete) == (None, None, False)
    assert ratio.net_minor is None  # the net fits, but an incomplete row has none


def test_missing_codes_keep_the_dec_order() -> None:
    cost = landed_cost(replace(EXAMPLE, unit_cost=Amount(4000, "CNY"), freight=None, duty_bps=None))
    assert cost.missing == ("freight_missing", "duty_not_set", "fx_missing")
    assert MISSING[-2:] == ("fx_missing", "amount_out_of_range")


def test_ddp_overridden_inputs_are_not_estimates() -> None:
    estimates = ("duty_bps", "customs_fee_minor", "returns_bps")
    ddp = landed_cost(replace(EXAMPLE, ddp=True, estimates=estimates))
    assert ddp.estimates == ("returns_bps",)
    assert landed_cost(replace(EXAMPLE, estimates=estimates)).estimates == tuple(sorted(estimates))


def test_a_freight_past_bigint_sorts_last_and_is_named() -> None:
    freight = Amount(2**63 - 1, "GBP", Decimal("0.5"))  # 1.8e19 USD cents
    assert cheapest(("A", freight, {})) == (True, 0)
    assert landed_cost(replace(EXAMPLE, freight=freight)).missing == ("amount_out_of_range",)


def test_ad_cost_turns_the_break_even_cpa_into_net_profit() -> None:
    cost = landed_cost(replace(EXAMPLE, ad_cost_minor=1500))  # the Profit note's CPA $15.00
    assert (cost.margin_minor, cost.ad_cost_minor, cost.net_minor, cost.net_bps) == (
        1503,
        1500,
        3,
        10,  # 3 / 2999 = 0.1%
    )
    loss = landed_cost(replace(EXAMPLE, ad_cost_minor=2000))
    assert (loss.net_minor, loss.net_bps) == (-497, -1657)  # -16.572%
    assert (landed_cost(EXAMPLE).net_minor, landed_cost(EXAMPLE).net_bps) == (1503, 5012)


def test_an_incomplete_row_has_no_net_profit() -> None:
    cost = landed_cost(replace(EXAMPLE, duty_bps=None, ad_cost_minor=1500))
    assert (cost.ad_cost_minor, cost.net_minor, cost.net_bps) == (1500, None, None)


def test_a_net_past_bigint_is_named() -> None:
    top = 2**63 - 1  # a $10,000 price keeps margin_bps in range, so only the net falls out
    near = replace(
        EXAMPLE,
        price_minor=1_000_000,
        unit_cost=Amount(top - 2000, "USD"),
        freight=Amount(0, "USD"),
        duty_bps=0,
    )
    assert landed_cost(near).margin_minor == -top + 922_970
    cost = landed_cost(replace(near, ad_cost_minor=1_000_000))  # net = -top - 77_030
    assert (cost.net_minor, cost.margin_minor, cost.missing) == (
        None,
        None,
        ("amount_out_of_range",),
    )
