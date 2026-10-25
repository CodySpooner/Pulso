"""The one landed-cost function (UX-8, R-16, DEC-246): pure, no I/O, no floats.

Every line is computed exactly and rounded half-even once, to USD cents; totals are sums of
the rounded lines, so a breakdown always adds up. A missing input leaves its line None, names
itself in `missing`, and withholds the totals that need it: never a guessed number.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction

from pulso_core.money import convert_minor

BPS = 10_000


@dataclass(frozen=True)
class Amount:
    """Minor units of `currency`; `usd_rate` is currency per 1 USD on the observation's UTC date."""

    minor: int
    currency: str
    usd_rate: Decimal | None = None


@dataclass(frozen=True)
class Inputs:
    price_minor: int | None  # USD retail price per order of `quantity` units
    unit_cost: Amount | None  # supplier cost of one unit
    freight: Amount | None  # the quote for exactly this variant and quantity to the US
    duty_bps: int | None  # None: duty not set (never an assumed 0)
    quantity: int = 1
    ddp: bool = False  # duties paid in the freight: zeroes duty and the customs fee
    customs_fee_minor: int = 0  # USD per order
    payment_fee_bps: int = 0
    payment_fee_fixed_minor: int = 0  # USD per order
    shopify_fee_bps: int = 0
    returns_bps: int = 0  # share of revenue refunded; goods and freight are not recovered
    freight_gap: str = "freight_missing"  # the loader's reason when `freight` is None
    estimates: tuple[str, ...] = ()  # inputs that are labelled owner estimates


@dataclass(frozen=True)
class LandedCost:
    price_minor: int | None
    goods_minor: int | None
    freight_minor: int | None
    duty_minor: int | None
    customs_fee_minor: int
    payment_fee_minor: int | None
    shopify_fee_minor: int | None
    returns_minor: int | None
    landed_cost_minor: int | None
    margin_minor: int | None  # contribution before ads: break-even CPA
    margin_bps: int | None
    complete: bool
    missing: tuple[str, ...]
    estimates: tuple[str, ...]


def bps_of(minor: int, bps: int) -> int:
    return round(Fraction(minor * bps, BPS))  # exact; round() on a Fraction is half-even


def to_usd(amount: Amount) -> int | None:
    """USD cents rounded half-even once; None when a non-USD amount has no rate."""
    if amount.currency == "USD":
        return amount.minor
    if amount.usd_rate is None:
        return None
    return convert_minor(
        amount.minor,
        amount.currency,
        "USD",
        amount.usd_rate,
        rounding=ROUND_HALF_EVEN,
        inverse=True,
    )


def landed_cost(inputs: Inputs) -> LandedCost:
    missing: list[str] = []

    def usd(amount: Amount | None, gap: str) -> int | None:
        converted = None if amount is None else to_usd(amount)
        if converted is None:
            missing.append(gap if amount is None else "fx_missing")
        return converted

    price = inputs.price_minor
    if price is not None and price <= 0:
        raise ValueError("A retail price must be positive")
    if price is None:
        missing.append("price_missing")
    cost = inputs.unit_cost
    goods = usd(
        cost and Amount(inputs.quantity * cost.minor, cost.currency, cost.usd_rate),
        "supplier_cost_missing",
    )
    freight = usd(inputs.freight, inputs.freight_gap)
    duty: int | None = 0
    if not inputs.ddp:
        if inputs.duty_bps is None:
            missing.append("duty_not_set")
        duty = None if inputs.duty_bps is None or goods is None else bps_of(goods, inputs.duty_bps)
    customs = 0 if inputs.ddp else inputs.customs_fee_minor
    lines = (goods, freight, duty)
    landed = None if None in lines else sum(line or 0 for line in lines) + customs

    payment = shopify = returns = margin = margin_bps = None
    if price is not None:
        payment = bps_of(price, inputs.payment_fee_bps) + inputs.payment_fee_fixed_minor
        shopify = bps_of(price, inputs.shopify_fee_bps)
        returns = bps_of(price, inputs.returns_bps)
        if landed is not None:
            margin = price - landed - payment - shopify - returns
            margin_bps = round(Fraction(margin * BPS, price))
    return LandedCost(
        price_minor=price,
        goods_minor=goods,
        freight_minor=freight,
        duty_minor=duty,
        customs_fee_minor=customs,
        payment_fee_minor=payment,
        shopify_fee_minor=shopify,
        returns_minor=returns,
        landed_cost_minor=landed,
        margin_minor=margin,
        margin_bps=margin_bps,
        complete=not missing,
        missing=tuple(dict.fromkeys(missing)),
        estimates=tuple(sorted(inputs.estimates)),
    )


def best[K](costs: Mapping[K, LandedCost]) -> K | None:
    """The key of the highest margin among complete rows; an incomplete row never wins (R-16)."""
    margins = {key: cost.margin_minor for key, cost in costs.items() if cost.complete}
    return max(margins, key=lambda key: margins[key] or 0, default=None)
