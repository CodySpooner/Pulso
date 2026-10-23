"""Pure storefront parsing and append-only catalog observations (no demand estimates)."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, Field, StrictBool, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import (
    Image,
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    Store,
    VariantSnapshot,
)
from pulso_core.money import to_minor
from pulso_sources.framework import UpsertStats, append_observation
from pulso_sources.shopify_stores.variants import CATALOG_WRITER, JSProduct, upsert_variants


class Variant(BaseModel):
    id: StrictInt = Field(gt=0)
    title: str | None = None  # an import may omit it; live parse() requires it
    price: str = Field(pattern=r"^[0-9]+(?:\.[0-9]+)?$")
    compare_at_price: str | None = Field(default=None, pattern=r"^[0-9]+(?:\.[0-9]+)?$")
    available: StrictBool | None
    sku: str | None = None
    option1: str | None = None
    option2: str | None = None
    option3: str | None = None
    updated_at: AwareDatetime | None = None


class ProductImage(BaseModel):
    src: str = Field(pattern=r"^https?://")
    position: int = Field(ge=1)


class Product(BaseModel):
    id: StrictInt = Field(gt=0)
    title: str = Field(min_length=1)
    handle: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    vendor: str | None = None
    product_type: str | None = None
    tags: list[str] = []
    created_at: AwareDatetime | None = None
    published_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None
    variants: list[Variant] = Field(min_length=1)
    images: list[ProductImage] = []


class Catalog(BaseModel):
    products: list[Product] = Field(max_length=250)


class Meta(BaseModel):
    id: StrictInt = Field(gt=0)
    myshopify_domain: str = Field(pattern=r"^[a-z0-9-]+\.myshopify\.com$")
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")


def parse(body: bytes) -> Sequence[Product | Meta | JSProduct]:
    text = body.decode("utf-8-sig").strip()
    if (
        not text
        or all(
            not line.split("#", 1)[0].strip() or ":" in line.split("#", 1)[0]
            for line in text.splitlines()
        )
        and "user-agent:" in text.lower()
        and "<" not in text
    ):
        return []  # robots.txt or the empty body of a 304
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Expected storefront object")
    if "variants" in data:
        product = JSProduct.model_validate(data)
        if len({v.id for v in product.variants}) != len(product.variants):
            raise ValueError("Duplicate variant identity")
        return [product]
    if "products" not in data:
        return [Meta.model_validate(data)]
    products = Catalog.model_validate(data).products
    if len({p.id for p in products}) != len(products) or any(
        len({v.id for v in p.variants}) != len(p.variants) for p in products
    ):
        raise ValueError("Duplicate catalog identity")
    if any(v.title is None or v.available is None for p in products for v in p.variants):
        raise ValueError("Live variants require title and availability")
    return products


def current(row: Listing | ListingVariant, at: datetime) -> bool:
    return all(at >= t.replace(tzinfo=UTC) for t in (row.last_seen_at, row.delisted_at) if t)


def utc_day(at: datetime) -> date:
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).astimezone(UTC).date()


def upsert(
    session: Session,
    records: Sequence[Product | Meta | JSProduct],
    payload: RawPayload,
    *,
    parser_version: str,
    store: Store | None = None,
    currency: str | None = None,
    observed_for: date | None = None,
) -> UpsertStats:
    imported = store is not None
    path = "/products.json?import" if imported else payload.request["path"]
    if str(path).endswith(".js"):
        if len(records) != 1 or not isinstance(records[0], JSProduct):
            raise ValueError("Payload does not match requested endpoint")
        return upsert_variants(session, records[0], payload, parser_version=parser_version)
    if (
        (path == "/robots.txt" and records)
        or (path == "/meta.json" and (len(records) != 1 or not isinstance(records[0], Meta)))
        or (str(path).startswith("/products.json?") and any(isinstance(r, Meta) for r in records))
    ):
        raise ValueError("Payload does not match requested endpoint")
    store = store or session.get_one(Store, payload.request["store_id"])
    currency = currency or store.currency
    day = observed_for or payload.captured_at.date()

    def refresh(row: Listing | ListingVariant, new: bool) -> bool:
        """Whether this capture's text replaces the row's. A live catalog is a sighting and
        relists; an import (DEC-162) never relists or moves last_seen_at, and its text wins
        only for a new row or evidence dated on or after the last sighting's UTC day."""
        if not imported:
            if current(row, payload.captured_at):
                row.last_seen_at, row.delisted_at = payload.captured_at, None
                return True
            return False
        if new:
            row.last_seen_at = payload.captured_at
        return new or day >= utc_day(row.last_seen_at)

    inserted = unchanged = 0
    for record in records:
        if isinstance(record, JSProduct):
            raise ValueError("Payload does not match requested endpoint")
        if isinstance(record, Meta):
            to_minor("0", record.currency)  # Reject unsupported currencies before catalog prices.
            store.shop_id, store.currency = str(record.id), record.currency
            store.myshopify_domain, store.country = record.myshopify_domain, record.country
            continue
        if not store.shop_id or not currency:
            raise ValueError("Store qualification required")
        listing = session.scalar(
            select(Listing).filter_by(
                source_id=payload.source_id, external_id=f"{store.shop_id}:{record.id}"
            )
        )
        new = listing is None
        if listing is None:
            listing = Listing(
                source_id=payload.source_id,
                external_id=f"{store.shop_id}:{record.id}",
                store_id=store.id,
                first_seen_at=payload.captured_at,
            )
            session.add(listing)
        elif listing.store_id != store.id:
            raise ValueError("Catalog identity belongs to another store")
        if refresh(listing, new):
            for name in ("title", "handle", "vendor", "product_type"):
                if not imported or name in record.model_fields_set:
                    setattr(listing, name, getattr(record, name))
            for name in ("tags", "created_at", "published_at"):
                if not imported or name in record.model_fields_set:
                    setattr(listing, f"source_{name}", getattr(record, name))
            listing.url = f"https://{store.domain}/products/{record.handle}"
        session.flush()
        values: list[dict[str, Any]] = []
        for item in record.variants:
            variant = session.scalar(
                select(ListingVariant).filter_by(listing_id=listing.id, external_id=str(item.id))
            )
            new = variant is None
            if variant is None:
                variant = ListingVariant(
                    listing_id=listing.id,
                    external_id=str(item.id),
                    first_seen_at=payload.captured_at,
                )
                session.add(variant)
            if refresh(variant, new):
                for name in ("title", "sku", "option1", "option2", "option3"):
                    if not imported or name in item.model_fields_set:
                        setattr(variant, name, getattr(item, name))
            session.flush()
            values.append(
                dict(
                    variant_id=variant.id,
                    price_minor=to_minor(item.price, currency),
                    compare_at_minor=to_minor(item.compare_at_price, currency)
                    if item.compare_at_price
                    else None,
                    available=item.available,
                    source_updated_at=item.updated_at,
                )
            )
        compare = [v["compare_at_minor"] for v in values if v["compare_at_minor"] is not None]
        listing_values = dict(
            listing_id=listing.id,
            price_min_minor=min(v["price_minor"] for v in values),
            price_max_minor=max(v["price_minor"] for v in values),
            compare_at_min_minor=min(compare) if compare else None,
            available=True
            if any(v["available"] for v in values)
            else (False if all(v["available"] is False for v in values) else None),
            source_updated_at=record.updated_at,
        )
        # DEC-162: an import aggregates the product only when it lists every listed variant.
        whole = not imported or set(
            session.scalars(
                select(ListingVariant.id).filter_by(listing_id=listing.id, delisted_at=None)
            )
        ) <= {v["variant_id"] for v in values}
        snapshots: list[tuple[type[ListingSnapshot] | type[VariantSnapshot], dict[str, Any]]] = [
            *([(ListingSnapshot, listing_values)] if whole else []),
            *[(VariantSnapshot, v) for v in values],
        ]
        for model, fields in snapshots:
            fields["currency"] = currency
            changed = append_observation(
                session,
                model(
                    **fields,
                    captured_at=payload.captured_at,
                    observed_for=observed_for or payload.captured_at.date(),
                    raw_payload_id=payload.id,
                    parser_version=parser_version,
                    values_hash=hashlib.sha256(
                        json.dumps(fields, sort_keys=True, default=str).encode()
                    ).hexdigest(),
                ),
                writer=CATALOG_WRITER if model is VariantSnapshot else None,
            )
            inserted += changed
            unchanged += not changed
        for image in record.images:
            existing = session.scalar(select(Image).filter_by(listing_id=listing.id, url=image.src))
            if existing is None:
                session.add(Image(listing_id=listing.id, url=image.src, position=image.position))
    return UpsertStats(inserted=inserted, unchanged=unchanged)
