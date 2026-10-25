"""Resolve landed_cost() inputs from the database (UX-8, R-16, DEC-246).

No fallbacks: an input that doesn't resolve stays None and landed_cost() names it in
`missing`. Freight is the exact variant and quantity quote to the US, never q x F(1).
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from pulso_core.landed_cost import (
    DDP_ZEROED,
    Amount,
    Inputs,
    LandedCost,
    best,
    landed_cost,
    to_usd,
)
from pulso_core.models import (
    FxRate,
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    ShippingOption,
    Source,
    VariantSnapshot,
    WorkspaceSettings,
)

FX_LOOKBACK = timedelta(days=4)  # bridges a weekend or holiday; older is "FX missing"
SETTINGS = {  # landed_cost() input: its settings column
    "duty_bps": "duty_default_bps",
    "customs_fee_minor": "customs_fee_minor",
    "payment_fee_bps": "payment_fee_bps",
    "payment_fee_fixed_minor": "payment_fee_fixed_minor",
    "shopify_fee_bps": "shopify_fee_bps",
    "returns_bps": "returns_bps",
}


@dataclass(frozen=True)
class Provenance:
    source: str  # sources.key, or "settings" / "owner_estimate" for owner input
    as_of: datetime | None = None  # the observation's captured_at; None for owner input
    raw_payload_id: int | None = None


@dataclass(frozen=True)
class Calc:
    listing_id: int | None  # the supplier listing costed; None when the product has none
    method: str | None  # the freight quote's shipping method
    cost: LandedCost
    sources: dict[str, Provenance]


def traced(session: Session, row: Row[Any], name: str) -> tuple[Amount, dict[str, Provenance]]:
    """An observed amount with its FX rate for the observation's UTC date (DEC-036)."""
    found = {name: Provenance(row.key, row.captured_at, row.raw_payload_id)}
    if row.currency == "USD":
        return Amount(row.minor, "USD"), found
    day = row.captured_at.astimezone(UTC).date()
    # The rate's own date, not its capture time: the daily job usually stores day d's rate on d + 1.
    rate = session.execute(
        select(FxRate.rate, FxRate.captured_at, FxRate.raw_payload_id, Source.key)
        .join(RawPayload, RawPayload.id == FxRate.raw_payload_id)
        .join(Source, Source.id == RawPayload.source_id)
        .where(
            FxRate.base == "USD",
            FxRate.quote == row.currency,
            FxRate.date.between(day - FX_LOOKBACK, day),
        )  # the newest date; on a tie, the daily job's blend before a manual CSV rate
        .order_by(FxRate.date.desc(), FxRate.source == "manual", FxRate.captured_at.desc())
        .limit(1)
    ).first()
    if rate is not None:
        found[f"fx_{name}"] = Provenance(rate.key, rate.captured_at, rate.raw_payload_id)
    return Amount(row.minor, row.currency, rate.rate if rate else None), found


def unit_cost(session: Session, listing_id: int, variant_id: int | None) -> Row[Any] | None:
    """The latest supplier price: the variant's when one is chosen, else the listing's."""
    snap: type[VariantSnapshot] | type[ListingSnapshot] = ListingSnapshot
    price, where = ListingSnapshot.price_min_minor, ListingSnapshot.listing_id == listing_id
    if variant_id is not None:
        snap, price, where = (
            VariantSnapshot,
            VariantSnapshot.price_minor,
            VariantSnapshot.variant_id == variant_id,
        )
    row = session.execute(
        select(
            price.label("minor"), snap.currency, snap.captured_at, snap.raw_payload_id, Source.key
        )
        .join(RawPayload, RawPayload.id == snap.raw_payload_id)
        .join(Source, Source.id == RawPayload.source_id)
        .where(where)
        .order_by(snap.captured_at.desc(), snap.id.desc())
        .limit(1)
    ).first()
    return row if row is not None and row.minor is not None else None


def freight_quotes(
    session: Session, listing_id: int, variant_id: int | None, quantity: int, method: str | None
) -> tuple[list[Row[Any]], str]:
    """The exact US quotes of the newest capture per origin on the variant's newest capture day,
    and the reason when there are none.

    A method the newest capture no longer lists is never priced (XR-16, DEC-250), and neither is
    an origin with nothing on that day: an empty answer writes no row (XR-23, DEC-258).
    """
    variants = session.scalars(
        select(ListingVariant.id).where(
            ListingVariant.listing_id == listing_id, ListingVariant.delisted_at.is_(None)
        )
    ).all()
    single = len(variants) <= 1  # only a single-variant listing takes a null-variant quote
    wanted = variant_id if variant_id is not None or not single else next(iter(variants), None)
    # One freight question per variant and origin; on a single-variant listing a null-variant
    # quote asks the variant's, so the two share one newest capture.
    variant = func.coalesce(ShippingOption.variant_id, wanted if single else None)
    newest = (
        select(
            ShippingOption.id,
            ShippingOption.variant_id,
            ShippingOption.origin_country,
            ShippingOption.method,
            ShippingOption.cost_minor.label("minor"),
            ShippingOption.currency,
            ShippingOption.captured_at,
            ShippingOption.raw_payload_id,
            ShippingOption.observed_for,
            Source.key,
            # CJ asks every origin in one run, so a day's captures are the variant's answer.
            func.max(ShippingOption.observed_for).over(partition_by=variant).label("day"),
            func.rank()  # 1 for every row of the origin's newest capture
            .over(
                partition_by=(variant, ShippingOption.origin_country),
                order_by=(
                    ShippingOption.observed_for.desc(),
                    ShippingOption.captured_at.desc(),
                    ShippingOption.raw_payload_id.desc(),
                ),
            )
            .label("capture"),
        )
        .join(RawPayload, RawPayload.id == ShippingOption.raw_payload_id)
        .join(Source, Source.id == RawPayload.source_id)
        .where(
            ShippingOption.listing_id == listing_id,
            ShippingOption.destination_country == "US",
            ShippingOption.quantity == quantity,
        )
        .subquery()
    )
    query = (
        select(newest)
        .where(newest.c.capture == 1, newest.c.observed_for == newest.c.day)
        .order_by(newest.c.id.desc())
    )
    if method is not None:  # after the ranking: a method's own last capture isn't the newest
        query = query.where(newest.c.method == method)
    quotes = session.execute(query).all()
    latest: dict[tuple[str | None, str], Row[Any]] = {}
    for quote in quotes:
        if (quote.variant_id is None and single) or (
            quote.variant_id is not None and quote.variant_id == wanted
        ):
            latest.setdefault((quote.origin_country, quote.method), quote)
    if not latest:
        return [], "freight_variant_mismatch" if quotes else "freight_missing"
    return list(latest.values()), "freight_missing"


def cheapest(option: tuple[str, Amount, dict[str, Provenance]]) -> tuple[bool, int]:
    """Without a chosen method, the cheapest quote in USD; one without FX sorts last."""
    try:
        usd = to_usd(option[1])
    except ValueError:  # past BIGINT: sorts last too, and landed_cost() names it (XR-20)
        usd = None
    return usd is None, usd or 0


def calculate(
    session: Session,
    settings: WorkspaceSettings,
    product_id: UUID,
    *,
    reference_price: tuple[int, Provenance] | None = None,
    overrides: Mapping[str, int] | None = None,
    listing_id: int | None = None,
    variant_id: int | None = None,
    quantity: int = 1,
    method: str | None = None,
    ddp: bool = False,
) -> Calc:
    """Cost a supplier listing of the product, or, without one, its best complete supplier.

    `overrides` are owner estimates by landed_cost() input name (including `price_minor`).
    Raises LookupError for a listing or variant that isn't on this product.
    """
    overrides = dict(overrides or {})
    values: dict[str, Any] = {"price_minor": None}
    values |= {name: getattr(settings, column) for name, column in SETTINGS.items()}
    sources = {name: Provenance("settings") for name, value in values.items() if value is not None}
    if reference_price is not None:
        values["price_minor"], sources["price_minor"] = reference_price
    values |= overrides
    sources |= {name: Provenance("owner_estimate") for name in overrides}
    if ddp:  # DDP zeroes duty and the customs fee, so neither input is used (XR-21)
        sources = {name: trace for name, trace in sources.items() if name not in DDP_ZEROED}
    base = Inputs(
        **values,
        unit_cost=None,
        freight=None,
        quantity=quantity,
        ddp=ddp,
        estimates=tuple(overrides),
    )

    listings = session.scalars(
        select(Listing.id)
        .where(
            Listing.product_id == product_id,
            Listing.supplier_id.is_not(None),
            Listing.delisted_at.is_(None),
        )
        .order_by(Listing.id)
    ).all()
    if listing_id is not None:
        if listing_id not in listings:
            raise LookupError("Supplier listing not found on this product.")
        listings = [listing_id]
    if variant_id is not None and (
        listing_id is None
        or listing_id
        != session.scalar(select(ListingVariant.listing_id).where(ListingVariant.id == variant_id))
    ):
        raise LookupError("Variant not found on this supplier listing.")

    calcs: dict[int, Calc] = {}
    for listing in listings:
        found = dict(sources)
        unit = None
        if (row := unit_cost(session, listing, variant_id)) is not None:
            unit, traces = traced(session, row, "unit_cost")
            found |= traces
        quotes, gap = freight_quotes(session, listing, variant_id, quantity, method)
        options = [(quote.method, *traced(session, quote, "freight")) for quote in quotes]
        chosen, freight = None, None
        if options:
            chosen, freight, traces = min(options, key=cheapest)
            found |= traces
        cost = landed_cost(replace(base, unit_cost=unit, freight=freight, freight_gap=gap))
        calcs[listing] = Calc(listing, chosen, cost, found)
    if not calcs:
        return Calc(None, None, landed_cost(base), sources)
    pick = best({listing: calc.cost for listing, calc in calcs.items()})
    if pick is None:  # nothing complete: the fewest missing inputs, then the lowest id
        pick = min(calcs, key=lambda listing: len(calcs[listing].cost.missing))
    return calcs[pick]
