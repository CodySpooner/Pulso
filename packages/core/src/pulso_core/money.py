"""Exact money parsing; FX conversion requires an explicit rounding mode."""

from decimal import Decimal, localcontext

CURRENCY_EXPONENTS = {
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "CAD": 2,
    "AUD": 2,
    "CNY": 2,
    "JPY": 0,
    "KWD": 3,
}


def to_minor(amount: Decimal | str | int, currency: str) -> int:
    if isinstance(amount, (float, bool)):
        raise TypeError("Use Decimal, a decimal string, or an integer for money")
    value = Decimal(amount)
    if not value.is_finite():
        raise ValueError("Money must be finite")
    exponent = CURRENCY_EXPONENTS[currency]
    with localcontext() as context:
        context.prec = max(28, len(value.as_tuple().digits) + exponent + 1)
        scaled = value * 10**exponent
    if scaled != scaled.to_integral_value():
        raise ValueError("Amount has fractional minor units")
    if not -(2**63) <= scaled < 2**63:
        raise ValueError("Amount exceeds BIGINT range")
    return int(scaled)


def from_minor(amount_minor: int, currency: str) -> Decimal:
    if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
        raise TypeError("Minor units must be an integer")
    return Decimal(amount_minor).scaleb(-CURRENCY_EXPONENTS[currency])


def convert_minor(amount_minor: int, base: str, quote: str, rate: Decimal, *, rounding: str) -> int:
    """Convert using quote major units per base unit, rounding only the final amount."""
    amount = from_minor(amount_minor, base)
    to_minor(amount, base)
    if not isinstance(rate, Decimal):
        raise TypeError("FX rate must be Decimal")
    if not rate.is_finite() or rate <= 0:
        raise ValueError("FX rate must be finite and positive")
    with localcontext() as context:
        context.prec = max(28, len(str(abs(amount_minor))) + len(rate.as_tuple().digits) + 6)
        converted = (amount * rate).quantize(
            Decimal(1).scaleb(-CURRENCY_EXPONENTS[quote]), rounding=rounding
        )
        return to_minor(converted, quote)
