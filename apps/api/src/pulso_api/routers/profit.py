"""Profit calculator (UX-8 part a): landed_cost() over workspace settings and owner estimates."""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.routers.account import BasisPoints, MinorUnits, workspace_settings
from pulso_api.routers.products import is_stale, latest_snapshots
from pulso_api.schemas.text import NoNulStr
from pulso_core.landed_cost_loader import Provenance, calculate
from pulso_core.models import Product, Source

router = APIRouter(prefix="/v1/profit")
Id = Annotated[int, Field(ge=1, le=2**63 - 1, strict=True)]
Missing = Literal[
    "price_missing",
    "supplier_cost_missing",
    "freight_missing",
    "freight_variant_mismatch",
    "duty_not_set",
    "fx_missing",
    "amount_out_of_range",
]
# Scenario overrides: each is a labelled owner estimate in the result.
OVERRIDES = {
    "price_minor",
    "duty_bps",
    "customs_fee_minor",
    "payment_fee_bps",
    "payment_fee_fixed_minor",
    "shopify_fee_bps",
    "returns_bps",
    "ad_cost_minor",
}
OWNER = {"settings": "Workspace settings", "owner_estimate": "Your estimate"}  # source_name


class ProfitScenario(BaseModel):
    """A Profit calc's inputs for a product named elsewhere (the Testing Board's snapshot)."""

    model_config = ConfigDict(extra="forbid")
    supplier_listing_id: Id | None = Field(
        None,
        description="A supplier listing of the product (supplier_offers.listing_id). "
        "Omitted: the supplier with the best complete margin.",
    )
    variant_id: Id | None = Field(None, description="A variant of `supplier_listing_id`.")
    quantity: int = Field(1, ge=1, le=10000, strict=True, description="Units per order.")
    method: NoNulStr | None = Field(
        None, min_length=1, max_length=200, description="Omitted: the cheapest exact quote."
    )
    ddp: bool = Field(False, strict=True, description="Freight includes duties.")
    price_minor: Id | None = Field(
        None, description="USD per order. Omitted: the median live store price, at quantity 1."
    )
    duty_bps: Annotated[int, Field(ge=0, le=100_000, strict=True)] | None = None  # can pass 100%
    customs_fee_minor: MinorUnits | None = None
    payment_fee_bps: BasisPoints | None = None
    payment_fee_fixed_minor: MinorUnits | None = None
    shopify_fee_bps: BasisPoints | None = None
    returns_bps: BasisPoints | None = None
    ad_cost_minor: MinorUnits | None = Field(
        None, description="USD ad cost per order (CPA). Omitted: settings.default_cpa_minor."
    )


class ProfitCalcRequest(ProfitScenario):
    product_id: UUID


class InputSource(BaseModel):
    source: str = Field(description="sources.key, or `settings` / `owner_estimate`.")
    source_name: str
    as_of: AwareDatetime | None  # the observation's capture; null for owner input
    raw_payload_id: int | None
    stale: bool  # as_of is older than twice the source's expected interval (DEC-238)


class ProfitCalc(BaseModel):
    product_id: UUID
    supplier_listing_id: int | None
    in_stock: bool = Field(
        description="The costed listing isn't known to be out of stock (DEC-243). False on the "
        "default when no supplier is in stock (DEC-291), or on a chosen sold-out listing; true "
        "with no listing."
    )
    variant_id: int | None
    quantity: int
    method: str | None  # the freight quote's shipping method
    freight_quote_id: int | None = Field(description="The shipping_options row freight uses.")
    freight_min_days: int | None  # the freight quote's delivery days
    freight_max_days: int | None
    ddp: bool
    currency: Literal["USD"]  # of every *_minor line
    price_minor: int | None
    goods_minor: int | None
    freight_minor: int | None
    duty_minor: int | None
    customs_fee_minor: int
    payment_fee_minor: int | None
    shopify_fee_minor: int | None
    returns_minor: int | None
    landed_cost_minor: int | None
    margin_minor: int | None = Field(description="Before ads: the break-even CPA. Complete only.")
    margin_bps: int | None
    ad_cost_minor: int
    net_minor: int | None = Field(description="After `ad_cost_minor`: net profit per order.")
    net_bps: int | None
    # The rates the lines use, from settings or the request; duty null: not set, or unused (DDP).
    duty_bps: int | None
    payment_fee_bps: int
    payment_fee_fixed_minor: int
    shopify_fee_bps: int
    returns_bps: int
    complete: bool
    missing: list[Missing]
    estimates: list[str]  # inputs that are labelled owner estimates
    sources: dict[str, InputSource]  # by input name
    as_of: AwareDatetime | None = Field(
        description="The oldest observation in `sources` (DEC-259); null when only settings "
        "and owner estimates feed the result."
    )


def reference_price(session: Session, product_id: UUID) -> tuple[int, Provenance] | None:
    """The median live USD store price: the lower middle, one listing's price with its trace."""
    rows = sorted(
        (
            row
            for row in latest_snapshots(session, [product_id])[product_id]
            if row.store_id is not None and row.currency == "USD" and (row.price_min_minor or 0) > 0
        ),
        key=lambda row: row.price_min_minor,
    )
    if not rows:
        return None
    row = rows[(len(rows) - 1) // 2]
    return row.price_min_minor, Provenance(row.key, row.captured_at, row.raw_payload_id)


@router.post("/calc", response_model=ProfitCalc)
def calc_profit(
    body: ProfitCalcRequest,
    principal: Annotated[Principal, Depends(current_principal)],
    session: Annotated[Session, Depends(get_db)],
) -> ProfitCalc:
    product = session.get(Product, body.product_id)
    if product is None or product.merged_into_id is not None:
        raise APIError(404, "not_found", "Product not found.")
    try:
        calc = calculate(
            session,
            workspace_settings(session, principal),
            product.id,
            # A single-unit price never stands in for a q-unit order.
            reference_price=reference_price(session, product.id)
            if body.quantity == 1 and body.price_minor is None
            else None,
            overrides=body.model_dump(include=OVERRIDES, exclude_none=True),
            listing_id=body.supplier_listing_id,
            variant_id=body.variant_id,
            quantity=body.quantity,
            method=body.method,
            ddp=body.ddp,
        )
    except LookupError as exc:
        raise APIError(404, "not_found", str(exc)) from exc
    now = datetime.now(UTC)
    observed = {trace.source for trace in calc.sources.values()} - OWNER.keys()
    rows = session.execute(
        select(Source.key, Source.name, Source.config).where(Source.key.in_(observed))
    )
    names = {row.key: row for row in rows}

    def source(trace: Provenance) -> InputSource:
        row = names.get(trace.source)
        return InputSource(
            **asdict(trace),
            source_name=row.name if row else OWNER.get(trace.source, trace.source),
            stale=bool(row and trace.as_of and is_stale(row.config, trace.as_of, now)),
        )

    inputs = calc.inputs
    return ProfitCalc(
        product_id=product.id,
        supplier_listing_id=calc.listing_id,
        in_stock=calc.in_stock,
        variant_id=body.variant_id,
        quantity=body.quantity,
        method=calc.method,
        freight_quote_id=calc.quote_id,
        freight_min_days=calc.days[0],
        freight_max_days=calc.days[1],
        ddp=body.ddp,
        currency="USD",
        **asdict(calc.cost),
        duty_bps=None if body.ddp else inputs.duty_bps,
        payment_fee_bps=inputs.payment_fee_bps,
        payment_fee_fixed_minor=inputs.payment_fee_fixed_minor,
        shopify_fee_bps=inputs.shopify_fee_bps,
        returns_bps=inputs.returns_bps,
        sources={name: source(trace) for name, trace in calc.sources.items()},
        as_of=min((trace.as_of for trace in calc.sources.values() if trace.as_of), default=None),
    )
