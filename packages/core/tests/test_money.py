from decimal import Decimal

import pytest

from pulso_core.money import from_minor, to_minor


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
