"""Manual catalogs use real Shopify identities and the catalog observation writer."""

import re
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, RawPayload, Store
from pulso_core.money import CURRENCY_EXPONENTS
from pulso_sources.framework import Request, Response, UpsertStats
from pulso_sources.shopify_stores.records import Catalog, Product, upsert

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData, Row


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")
    store_domain: str = Field(pattern=r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$", max_length=253)
    shop_id: str = Field(pattern=r"^[1-9][0-9]*$")
    currency: str

    @field_validator("currency")
    @classmethod
    def supported_currency(cls, value: str) -> str:
        if value not in CURRENCY_EXPONENTS:
            raise ValueError("Unsupported currency")
        return value


def _store(session: Session, context: Context) -> Store:
    store = session.scalar(select(Store).filter_by(domain=context.store_domain))
    if store is None:
        store = Store(domain=context.store_domain, platform="shopify")
        session.add(store)
    if store.platform != "shopify" or store.shop_id not in (None, context.shop_id):
        raise ValueError("Shop identity conflicts with the stored domain")
    store.shop_id = context.shop_id
    store.currency = store.currency or context.currency
    session.flush()
    return store


class ShopifyImportAdapter:
    parser_version = "shopify-import-1"

    def __init__(self, data: ImportData) -> None:
        self.data = data

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise AssertionError("Imports never fetch")

    def parse(self, body: bytes) -> Sequence[Product | Row]:
        if self.data.csv is not None:
            return self.data.csv.rows
        products = Catalog.model_validate_json(body).products
        if len({p.id for p in products}) != len(products) or any(
            len({v.id for v in p.variants}) != len(p.variants) for p in products
        ):
            raise ValueError("Duplicate catalog identity")
        return products

    def upsert(
        self,
        session: Session,
        records: Sequence[Product | Row],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        context = Context.model_validate(payload.request.get("shopify_import"))
        store = _store(session, context)
        groups: dict[tuple[str, str], list[Row]] = defaultdict(list)
        products: list[tuple[Product, date | None]] = []
        for record in records:
            if isinstance(record, dict):
                domain, url = str(record["store_domain"]), str(record["product_url"])
                if domain != context.store_domain or record["currency"] != context.currency:
                    raise ValueError("Store or currency does not match import context")
                match = re.fullmatch(r"https://" + re.escape(domain) + r"/products/([\w-]+)", url)
                if match is None:
                    raise ValueError("Product URL must match the explicit store domain")
                groups[(domain, match[1])].append(record)
            else:
                products.append((record, self.data.observed_for))
        seen: set[tuple[int, int]] = set()
        for (_, handle), rows in groups.items():
            first = rows[0]
            product_id = first.get("product_id")
            identity = (
                {"external_id": f"{store.shop_id}:{product_id}"}
                if product_id
                else {"handle": handle}
            )
            listing = session.scalars(
                select(Listing).filter_by(
                    source_id=payload.source_id, store_id=store.id, **identity
                )
            ).one_or_none()
            if product_id is None:
                if listing is None:
                    raise ValueError("Unknown handle requires a Shopify product_id")
                product_id = listing.external_id.split(":")[1]
            variants: list[dict[str, Any]] = []
            for row in rows:
                if row.get("product_id", product_id) != product_id:
                    raise ValueError("Conflicting product identities")
                variant_id = row.get("variant_id")
                if variant_id is None:
                    if listing is None or not (row.get("sku") or row.get("variant_title")):
                        raise ValueError("Unknown variant requires a Shopify variant_id")
                    key = {"sku": row["sku"]} if row.get("sku") else {"title": row["variant_title"]}
                    variant_id = session.scalars(
                        select(ListingVariant.external_id).filter_by(listing_id=listing.id, **key)
                    ).one()
                compare = row.get("compare_at_price")
                variants.append(
                    dict(
                        id=int(str(variant_id)),
                        title=row.get("variant_title"),
                        price=format(row["price"], "f"),
                        available=row.get("available"),
                        **({"sku": row["sku"]} if "sku" in row else {}),
                        compare_at_price=format(compare, "f") if compare is not None else None,
                    )
                )
            product = Product.model_validate(
                dict(
                    id=int(str(product_id)), title=first["title"], handle=handle, variants=variants
                )
            )
            variant_ids = [v.id for v in product.variants]
            if (store.id, product.id) in seen or len(set(variant_ids)) != len(variant_ids):
                raise ValueError("Duplicate resolved Shopify identity")
            seen.add((store.id, product.id))
            observed_for = first.get("observed_for", payload.captured_at.date())
            assert isinstance(observed_for, date)  # parse_csv validates date cells.
            products.append((product, observed_for))
        inserted = unchanged = 0
        for product, day in products:
            stats = upsert(
                session,
                [product],
                payload,
                parser_version=parser_version,
                store=store,
                currency=context.currency,
                observed_for=day,
            )
            inserted += stats.inserted
            unchanged += stats.unchanged
        return UpsertStats(inserted=inserted, unchanged=unchanged)
