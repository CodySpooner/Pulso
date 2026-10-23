"""Bounded tracked-product observations; request metadata supplies stock/freight identity."""

import hashlib
import json
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, RawPayload, ShippingOption, VariantSnapshot
from pulso_core.money import to_minor
from pulso_sources.cj import CJAdapter, Identifier, Record
from pulso_sources.cj.errors import classify_error
from pulso_sources.cj.transport import FreightRequest, Transport
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    UpsertStats,
    Writer,
    append_observation,
)

# DEC-120: detail owns variant price and stock owns inventory; each is change-only alone.
DETAIL_WRITER = Writer(
    RawPayload.request["endpoint"].as_string() == "/product/query", ("price_minor",)
)
STOCK_WRITER = Writer(
    RawPayload.request["endpoint"].as_string() == "/product/stock/getInventoryByPid",
    ("inventory_quantity",),
)
VARIANT_WRITERS = (DETAIL_WRITER, STOCK_WRITER)

Count = Annotated[StrictInt, Field(ge=0, le=2**63 - 1)]
Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class Variant(BaseModel):
    vid: Identifier
    variantSku: str | None = None
    variantNameEn: str | None = None
    variantSellPrice: Money


class Detail(BaseModel):
    pid: Identifier
    productNameEn: Identifier
    sellPrice: str | Money
    listedNum: Count | None = None
    variants: list[Variant]


class Warehouse(BaseModel):
    countryCode: Annotated[str, Field(pattern=r"^[A-Z]{2}$")]
    totalInventory: Count


class StockVariant(BaseModel):
    vid: Identifier
    inventory: list[Warehouse] | None


class Stock(BaseModel):
    variantInventories: list[StockVariant]


class Freight(BaseModel):
    logisticName: Identifier
    logisticPrice: Money
    logisticAging: str | None = None


def plan(product_ids: Sequence[str], variant_ids: Sequence[str] = ()) -> list[Target]:
    """Caller supplies tracked IDs; two origins and unit quantity cap freight at 300 calls."""
    for ids, cap in ((product_ids, 300), (variant_ids, 150)):
        if len(ids) > cap or len(set(ids)) != len(ids) or any(not i.strip() for i in ids):
            raise ValueError("CJ tracked plan exceeds cap or has invalid/duplicate IDs")
    return [
        Target(
            "cj_tracked",
            pid,
            [
                Request(params={"endpoint": ep, "pid": pid})
                for ep in ("/product/query", "/product/stock/getInventoryByPid")
            ],
        )
        for pid in product_ids
    ] + [
        Target(
            "cj_freight_us",
            f"{vid}:{origin}",
            [
                Request(
                    params={
                        "endpoint": "/logistic/freightCalculate",
                        "startCountryCode": origin,
                        "endCountryCode": "US",
                        "products": [{"vid": vid, "quantity": 1}],
                    }
                )
            ],
        )
        for vid in variant_ids
        for origin in ("CN", "US")
    ]


def parse(body: bytes) -> list[Detail | Stock | Freight]:
    if error := classify_error(Response(body, 200)):
        raise error
    data = json.loads(body, parse_float=Decimal)["data"]
    if isinstance(data, list):
        quotes = TypeAdapter(list[Freight]).validate_python(data)
        if len({q.logisticName for q in quotes}) != len(quotes):
            raise ValueError("Duplicate CJ freight method")
        return list(quotes)
    record = Detail.model_validate(data) if "pid" in data else Stock.model_validate(data)
    variants = record.variants if isinstance(record, Detail) else record.variantInventories
    if len({v.vid for v in variants}) != len(variants):
        raise ValueError("Duplicate CJ variant")
    return [record]


class TrackedAdapter:
    parser_version = "cj-tracked-v1"
    parse = staticmethod(parse)

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        if self.transport is None:
            raise CollectorsLiveDisabled("CJ collection requires a guarded transport")
        return self.transport.fetch(request)

    def upsert(
        self,
        session: Session,
        records: Sequence[Detail | Stock | Freight],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        inserted = unchanged = 0
        evidence = dict(
            raw_payload_id=payload.id,
            captured_at=payload.captured_at,
            observed_for=payload.captured_at.date(),
            parser_version=parser_version,
        )
        for record in records:
            if isinstance(record, Detail):
                if payload.request.get("pid") != record.pid:
                    raise ValueError("CJ detail does not match requested product")
                amounts = str(record.sellPrice).split("-")
                low, high = to_minor(amounts[0], "USD"), to_minor(amounts[-1], "USD")
                if len(amounts) not in {1, 2} or low < 0 or high < low:
                    raise ValueError("Invalid CJ detail price range")
                stats = CJAdapter().upsert(
                    session,
                    [
                        Record(
                            external_id=record.pid,
                            title=record.productNameEn,
                            price_min_minor=low,
                            price_max_minor=high,
                            listed_count=record.listedNum,
                        )
                    ],
                    payload,
                    parser_version=parser_version,
                )
                inserted += stats.inserted
                unchanged += stats.unchanged
            if isinstance(record, Freight):
                request = FreightRequest.model_validate(payload.request)
                quoted_variant = session.scalars(
                    select(ListingVariant)
                    .join(Listing)
                    .where(
                        Listing.source_id == payload.source_id,
                        ListingVariant.external_id == request.products[0].vid,
                    )
                ).one()
                days = re.fullmatch(r"(\d+)(?:-(\d+))?", record.logisticAging or "")
                low_days, high_days = (
                    (int(days[1]), int(days[2] or days[1])) if days else (None, None)
                )
                if low_days is not None and high_days is not None and low_days > high_days:
                    raise ValueError("Invalid CJ freight time range")
                added = append_observation(
                    session,
                    ShippingOption(
                        listing_id=quoted_variant.listing_id,
                        variant_id=quoted_variant.id,
                        origin_country=request.startCountryCode,
                        destination_country="US",
                        quantity=1,
                        method=record.logisticName,
                        cost_minor=to_minor(record.logisticPrice, "USD"),
                        currency="USD",
                        min_days=low_days,
                        max_days=high_days,
                        **evidence,
                    ),
                )
                inserted += added
                unchanged += not added
                continue
            listing = session.scalars(
                select(Listing).filter_by(
                    source_id=payload.source_id, external_id=payload.request.get("pid")
                )
            ).one()
            variants = record.variants if isinstance(record, Detail) else record.variantInventories
            for value in variants:
                variant = session.scalar(
                    select(ListingVariant).filter_by(listing_id=listing.id, external_id=value.vid)
                )
                if variant is None:
                    if isinstance(value, StockVariant):
                        raise ValueError("CJ stock requires a known tracked variant")
                    variant = ListingVariant(
                        listing_id=listing.id,
                        external_id=value.vid,
                        first_seen_at=payload.captured_at,
                        last_seen_at=payload.captured_at,
                    )
                    session.add(variant)
                    session.flush()
                if isinstance(value, Variant):
                    if payload.captured_at >= variant.last_seen_at:
                        variant.sku, variant.title = value.variantSku, value.variantNameEn
                        variant.last_seen_at = payload.captured_at
                    values: dict[str, int | None] = {
                        "price_minor": to_minor(value.variantSellPrice, "USD")
                    }
                else:
                    countries = [w.countryCode for w in value.inventory or []]
                    if len(set(countries)) != len(countries):
                        raise ValueError("Duplicate CJ inventory country")
                    total = (
                        sum(w.totalInventory for w in value.inventory) if value.inventory else None
                    )
                    if total is not None and total >= 2**63:
                        raise ValueError("CJ stock exceeds BIGINT range")
                    values = {"inventory_quantity": total}
                added = append_observation(
                    session,
                    VariantSnapshot(
                        variant_id=variant.id,
                        currency="USD",
                        **evidence,
                        **values,
                        values_hash=hashlib.sha256(
                            json.dumps(values, sort_keys=True).encode()
                        ).hexdigest(),
                    ),
                    writer=DETAIL_WRITER if isinstance(value, Variant) else STOCK_WRITER,
                )
                inserted += added
                unchanged += not added
        return UpsertStats(inserted=inserted, unchanged=unchanged)
