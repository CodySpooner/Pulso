"""AE-3: the Suppliers tab's AliExpress live lookup (DEC-037, DEC-283, DEC-289).

Pulso stores no AliExpress id. The user pastes a product link; the answer lives only in Redis,
under the workspace's Pulso product, until lookup()'s own 24 h expiry. The only durable state is
the `aliexpress` source row's shared block state.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, Field
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB
from pulso_core.models import Product, Source
from pulso_core.settings import Settings, get_settings
from pulso_sources.aliexpress import Product as Item
from pulso_sources.aliexpress import Shipping, Sku
from pulso_sources.aliexpress.lookup import (
    DAILY_CALL_CAP,
    TTL_SECONDS,
    Answer,
    Transport,
    https_transport,
    lookup,
)
from pulso_sources.framework import CollectorsLiveDisabled

router = APIRouter(prefix="/v1/products")
DIGITS = r"[0-9]{1,30}"  # ASCII only, as lookup() requires
HOST = re.compile(r"(?:[a-z0-9-]+\.)*aliexpress\.(?:com|us)")
PATH = re.compile(rf"/item/({DIGITS})\.html")


# Renamed copies of lookup()'s models, so the OpenAPI schema never names a bare "Product". Each
# repeats the lookup's as_of: every number in a product resource carries one (Q-1, DEC-238).
class AliExpressSku(Sku):
    as_of: AwareDatetime


class AliExpressProduct(Item):
    skus: list[AliExpressSku]  # type: ignore[assignment]  # pydantic validates into the subclass
    as_of: AwareDatetime


class AliExpressShipping(Shipping):
    as_of: AwareDatetime


class AliExpressLookup(BaseModel):
    """`empty`: no lookup for this product in the last 24 h. `ok` and `not_found` carry `as_of`."""

    status: Literal["empty", "ok", "not_found", "disabled", "not_configured", "throttled", "error"]
    product: AliExpressProduct | None = None
    shipping: list[AliExpressShipping] | None = None  # None: the link named no SKU
    as_of: AwareDatetime | None = None
    expires_at: AwareDatetime | None = Field(None, description="as_of + 24 h: the rows go then.")
    retry_at: AwareDatetime | None = Field(None, description="throttled: the next lookup's time.")


class LookupRequest(BaseModel):
    link: str = Field(max_length=2048, description="An AliExpress product link or number.")


def get_cache(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[Redis]:
    with Redis.from_url(
        settings.redis_url.get_secret_value(), socket_connect_timeout=2, socket_timeout=2
    ) as client:
        yield client


def get_transport() -> Transport | None:
    return None  # lookup() then builds the HTTPS transport behind the collector guard (DEC-283 e)


Cache = Annotated[Redis, Depends(get_cache)]
Gateway = Annotated[Transport | None, Depends(get_transport)]
Config = Annotated[Settings, Depends(get_settings)]
Caller = Annotated[Principal, Depends(current_principal)]


def parse_link(link: str) -> tuple[str, str | None] | None:
    """The product id, and the SKU id when the link names one (`skuId=`)."""
    text = link.strip()
    if re.fullmatch(DIGITS, text):
        return text, None
    try:
        parts = urlsplit(text)
        host = parts.hostname or ""
    except ValueError:
        return None
    path = PATH.fullmatch(parts.path)
    if parts.scheme not in ("http", "https") or not HOST.fullmatch(host) or path is None:
        return None
    sku = parse_qs(parts.query).get("skuId", [""])[0]
    return path[1], sku if re.fullmatch(DIGITS, sku) else None


def _stamped(answer: Answer) -> dict[str, Any]:
    """The answer with its as_of on the product, each SKU and each shipping option."""
    data, stamp = answer.model_dump(), {"as_of": answer.as_of}
    if product := data["product"]:
        data["product"] = {**product, **stamp, "skus": [{**s, **stamp} for s in product["skus"]]}
    if data["shipping"] is not None:
        data["shipping"] = [{**option, **stamp} for option in data["shipping"]]
    return data


def _key(principal: Principal, product_id: UUID) -> str:
    return f"pulso:aliexpress:v1:lookup:{principal.workspace_id}:{product_id}"


def _product(session: Session, product_id: UUID) -> None:
    if session.get(Product, product_id) is None:
        raise APIError(404, "not_found", "Product not found.")


def _retry_at(session: Session, cache: Redis, at: datetime) -> datetime | None:
    source = session.scalar(select(Source).filter_by(key="aliexpress"))
    if source and source.retry_not_before and source.retry_not_before > at:
        return source.retry_not_before
    used = cache.get(f"pulso:aliexpress:calls:{at.date().isoformat()}")  # lookup()'s counter
    if isinstance(used, (bytes, str, int)) and int(used) >= DAILY_CALL_CAP:
        return datetime.combine(at.date() + timedelta(days=1), time(), UTC)
    return None


def _gate(
    session: Session, cache: Redis, settings: Settings, transport: Transport | None
) -> AliExpressLookup:
    """What a lookup would answer before calling AliExpress, in lookup()'s order."""
    if not (
        settings.aliexpress_app_key
        and settings.aliexpress_app_secret
        and settings.aliexpress_access_token
    ):
        return AliExpressLookup(status="not_configured")
    source = session.scalar(select(Source).filter_by(key="aliexpress"))
    if source is None or not source.enabled:
        return AliExpressLookup(status="disabled")
    if retry_at := _retry_at(session, cache, datetime.now(UTC)):
        return AliExpressLookup(status="throttled", retry_at=retry_at)
    if transport is None:
        try:
            https_transport(settings)  # builds the closure only; nothing is sent
        except CollectorsLiveDisabled:
            return AliExpressLookup(status="disabled")
    return AliExpressLookup(status="empty")


@router.get("/{product_id}/aliexpress", response_model=AliExpressLookup)
def get_product_aliexpress(
    product_id: UUID, session: DB, principal: Caller, settings: Config, cache: Cache,
    transport: Gateway,
) -> AliExpressLookup:  # fmt: skip
    """This product's last AliExpress lookup while its 24 h last, else whether one can run."""
    _product(session, product_id)
    if not settings.aliexpress_enabled:
        return AliExpressLookup(status="disabled")
    if isinstance(cached := cache.get(_key(principal, product_id)), (str, bytes)):
        return AliExpressLookup.model_validate_json(cached)
    return _gate(session, cache, settings, transport)


@router.post("/{product_id}/aliexpress", response_model=AliExpressLookup)
def lookup_product_aliexpress(
    product_id: UUID, body: LookupRequest, session: DB, principal: Caller, settings: Config,
    cache: Cache, transport: Gateway,
) -> AliExpressLookup:  # fmt: skip
    """Look up a pasted AliExpress link live; the answer is kept in Redis only, never stored."""
    _product(session, product_id)
    if (ids := parse_link(body.link)) is None:
        raise APIError(422, "invalid_link", "Paste an AliExpress product link or number.")
    answer = lookup(session, cache, *ids, settings=settings, transport=transport)
    if answer.status == "throttled":
        return AliExpressLookup(
            status="throttled", retry_at=_retry_at(session, cache, datetime.now(UTC))
        )
    expires_at = answer.as_of and answer.as_of + timedelta(seconds=TTL_SECONDS)
    result = AliExpressLookup.model_validate({**_stamped(answer), "expires_at": expires_at})
    if expires_at:  # ok and not_found: gone when lookup()'s own entry goes
        cache.set(_key(principal, product_id), result.model_dump_json(), exat=expires_at)
    return result
