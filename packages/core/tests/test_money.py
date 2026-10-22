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


def test_unknown_currency_is_not_assumed_to_have_two_decimals() -> None:
    with pytest.raises(KeyError):
        to_minor("1.23", "XYZ")


def test_fx_rounding_is_explicit_and_only_at_destination() -> None:
    assert convert_minor(1, "USD", "JPY", Decimal("150"), rounding=ROUND_HALF_EVEN) == 2
    assert convert_minor(1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_EVEN) == 0
    assert convert_minor(1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_UP) == 1
    assert convert_minor(-1, "USD", "USD", Decimal("0.5"), rounding=ROUND_HALF_UP) == -1
    assert convert_minor(100, "USD", "KWD", Decimal("0.3075"), rounding=ROUND_HALF_UP) == 308


@pytest.mark.parametrize("rate", ["0", "-1", "NaN", "Infinity"])
def test_fx_rejects_invalid_rate(rate: str) -> None:
    with pytest.raises(ValueError):
        convert_minor(100, "USD", "JPY", Decimal(rate), rounding=ROUND_HALF_EVEN)


def test_fx_rejects_noninteger_input_and_bigint_overflow() -> None:
    with pytest.raises(TypeError):
        convert_minor(True, "USD", "JPY", Decimal(1), rounding=ROUND_HALF_EVEN)
    for amount, rate in [(2**63, Decimal(1)), (2**62, Decimal(2))]:
        with pytest.raises(ValueError):
            convert_minor(amount, "USD", "USD", rate, rounding=ROUND_HALF_EVEN)
