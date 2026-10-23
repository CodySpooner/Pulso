"""Product .js observations; prices are minor units and missing inventory stays unknown."""

import hashlib
import json
from datetime import UTC

from pydantic import BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, RawPayload, Store, VariantSnapshot
from pulso_core.money import CURRENCY_EXPONENTS, from_minor, to_minor
from pulso_sources.framework import UpsertStats, append_observation


class JSVariant(BaseModel):
    id: StrictInt = Field(gt=0)
    price: StrictInt = Field(ge=0, le=2**63 - 1)
    compare_at_price: StrictInt | None = Field(default=None, ge=0, le=2**63 - 1)
    available: StrictBool
    inventory_quantity: StrictInt | None = Field(default=None, ge=-(2**63), le=2**63 - 1)
    inventory_management: str | None = None
    inventory_policy: str | None = None
    barcode: str | None = None


class JSProduct(BaseModel):
    id: StrictInt = Field(gt=0)
    handle: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    variants: list[JSVariant] = Field(min_length=1, max_length=250)


def upsert_variants(
    session: Session, product: JSProduct, payload: RawPayload, *, parser_version: str
) -> UpsertStats:
    store = session.get_one(Store, payload.request["store_id"])
    currency = payload.request["currency"]
    if not store.shop_id or currency not in CURRENCY_EXPONENTS:
        raise ValueError("Store qualification required")
    if payload.request["path"] != f"/products/{product.handle}.js":
        raise ValueError("Product does not match requested endpoint")
    listing = session.scalars(
        select(Listing).filter_by(
            id=payload.request["listing_id"],
            source_id=payload.source_id,
            store_id=store.id,
            external_id=f"{store.shop_id}:{product.id}",
            handle=product.handle,
        )
    ).one()

    def minor(value: int | None) -> int | None:
        # Shopify appends two decimal places even for zero-subunit currencies.
        if value is not None and CURRENCY_EXPONENTS[currency] == 0:
            return to_minor(from_minor(value, "USD"), currency)
        return value

    inserted = 0
    for item in product.variants:
        # shortcut: unknown variants wait for catalog; extend when incremental identity is needed.
        variant = session.scalars(
            select(ListingVariant).filter_by(listing_id=listing.id, external_id=str(item.id))
        ).one()

        fields = dict(
            variant_id=variant.id,
            currency=currency,
            price_minor=minor(item.price),
            compare_at_minor=minor(item.compare_at_price),
            available=item.available,
            inventory_quantity=item.inventory_quantity,
            inventory_management=item.inventory_management,
            inventory_policy=item.inventory_policy,
        )
        inserted += append_observation(
            session,
            VariantSnapshot(
                **fields,
                captured_at=payload.captured_at,
                observed_for=payload.captured_at.date(),
                raw_payload_id=payload.id,
                parser_version=parser_version,
                values_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest(),
            ),
        )
        if all(
            payload.captured_at >= at.replace(tzinfo=UTC)
            for at in (variant.last_seen_at, variant.delisted_at)
            if at
        ):
            if "barcode" in item.model_fields_set:
                variant.barcode = item.barcode
            variant.last_seen_at = payload.captured_at
    return UpsertStats(inserted=inserted, unchanged=len(product.variants) - inserted)
