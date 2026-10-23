from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import pytest

from pulso_core.money import convert_minor, from_minor, to_minor


@pytest.mark.parametrize(
    "currency,value,minor",
    [
        ("JPY", "123", 123),
        ("USD", "1.23", 123),
        ("KWD", "1.234", 1234),
        ("USD", "-1.23", -123),
        ("USD", "0", 0),
        ("JPY", "9223372036854775807", 2**63 - 1),
        ("JPY", "-9223372036854775808", -(2**63)),
        ("USD", "92233720368547758.07", 2**63 - 1),
        ("USD", "-92233720368547758.08", -(2**63)),
        ("KWD", "9223372036854775.807", 2**63 - 1),
        ("KWD", "-9223372036854775.808", -(2**63)),
    ],
)
def test_currency_roundtrip(currency: str, value: str, minor: int) -> None:
    assert to_minor(value, currency) == minor
    assert from_minor(minor, currency) == Decimal(value)


@pytest.mark.parametrize(
    "value",
    [
        "1.001",
        "NaN",
        "Infinity",
        "92233720368547758.08",
        "1.00000000000000000000000000001",
    ],
)
def test_invalid_money(value: str) -> None:
    with pytest.raises(ValueError):
        to_minor(value, "USD")


@pytest.mark.parametrize("value", [1.0, 1.23, True, False])
def test_to_minor_rejects_float_and_bool(value: object) -> None:
    with pytest.raises(TypeError, match="Use Decimal, a decimal string, or an integer for money"):
        to_minor(value, "USD")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [True, False, 100.0, "100", Decimal("100"), None])
def test_from_minor_rejects_noninteger_and_bool(value: object) -> None:
    with pytest.raises(TypeError, match="Minor units must be an integer"):
        from_minor(value, "USD")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "currency,value",
    [
        ("JPY", "9223372036854775808"),
        ("JPY", "-9223372036854775809"),
        ("USD", "92233720368547758.08"),
        ("USD", "-92233720368547758.09"),
        ("KWD", "9223372036854775.808"),
        ("KWD", "-9223372036854775.809"),
    ],
)
def test_to_minor_rejects_one_minor_unit_outside_bigint(currency: str, value: str) -> None:
    with pytest.raises(ValueError, match="Amount exceeds BIGINT range"):
        to_minor(value, currency)


def test_unknown_currency_is_not_assumed_to_have_two_decimals() -> None:
    with pytest.raises(KeyError):
        to_minor("1.23", "XYZ")


def test_fx_rounding_is_explicit_and_only_at_destination() -> None:
    assert convert_minor(1, "USD", "JPY", Decimal("150"), rounding=ROUND_HALF_EVEN) == 2
    assert convert_minor(1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_EVEN) == 0
    assert convert_minor(1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_UP) == 1
    assert convert_minor(-1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_UP) == -1
    assert convert_minor(100, "USD", "KWD", Decimal("0.3075"), rounding=ROUND_HALF_UP) == 308


def test_inverse_rate_rounds_the_exact_quotient_once() -> None:
    # P1-32 L6: EUR 12.12 at 0.96 EUR per USD is exactly USD 12.625; 1/rate double-rounds.
    rate = Decimal("0.96")
    assert convert_minor(1212, "EUR", "USD", rate, rounding=ROUND_HALF_EVEN, inverse=True) == 1262


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity"])
def test_fx_rejects_invalid_rate(rate: str) -> None:
    with pytest.raises(ValueError):
        convert_minor(100, "USD", "JPY", Decimal(rate), rounding=ROUND_HALF_EVEN)


@pytest.mark.parametrize("rate", [1, 1.0, "1", True])
def test_fx_rejects_nondecimal_rate(rate: object) -> None:
    with pytest.raises(TypeError, match="FX rate must be Decimal"):
        convert_minor(100, "USD", "JPY", rate, rounding=ROUND_HALF_EVEN)  # type: ignore[arg-type]


@pytest.mark.parametrize("amount", [-(2**63), 2**63 - 1])
def test_fx_preserves_bigint_endpoints_at_unit_rate(amount: int) -> None:
    assert convert_minor(amount, "USD", "USD", Decimal(1), rounding=ROUND_HALF_EVEN) == amount


def test_fx_rejects_noninteger_input_and_bigint_overflow() -> None:
    with pytest.raises(TypeError):
        convert_minor(True, "USD", "JPY", Decimal(1), rounding=ROUND_HALF_EVEN)
    for amount, rate in [
        (2**63, Decimal(1)),
        (-(2**63) - 1, Decimal(1)),
        (2**62, Decimal(2)),
        (-(2**62) - 1, Decimal(2)),
    ]:
        with pytest.raises(ValueError, match="Amount exceeds BIGINT range"):
            convert_minor(amount, "USD", "USD", rate, rounding=ROUND_HALF_EVEN)
