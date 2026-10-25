"""AliExpress DS client (AE-1, DEC-283): signing, request bodies and parsed answers.

Live lookup only (DEC-037): nothing here stores, captures or logs a payload. Rules come from the
Open Platform docs read 2026-10-25 (docs/DATA_SOURCES.md); the gateway was never called.
"""

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode

from pydantic import BaseModel

from pulso_core.money import to_minor
from pulso_sources.framework.lifecycle import BLOCK_STATUSES

HOST = "api-sg.aliexpress.com"
PRODUCT = "aliexpress.ds.product.get"
FREIGHT = "aliexpress.ds.freight.query"
SHIP_TO = "US"
CURRENCY = "USD"
# The documented throttle answer: "Api access frequency exceeds the limit. this ban will last 1
# seconds" (aliexpress.ds.product.get, Common Issues). Its error code is not documented.
THROTTLE = re.compile(r"frequency exceeds the limit.*?ban will last (\d+) seconds?", re.I | re.S)

type Failure = Literal["blocked", "revoked", "failed"]


class Sku(BaseModel):
    sku_id: str
    price_minor: int
    sale_price_minor: int
    currency: Literal["USD"] = "USD"
    stock: int | None


class Product(BaseModel):
    product_id: str
    title: str
    rating: Decimal | None
    review_count: int | None
    sales: str | None  # AliExpress's own label, e.g. "1000+"; window undocumented
    store_name: str | None
    skus: list[Sku]


class Shipping(BaseModel):
    code: str
    company: str
    fee_minor: int
    currency: Literal["USD"] = "USD"
    free: bool
    min_days: int | None
    max_days: int | None
    ship_from: str | None


def sign(params: Mapping[str, str], secret: str, api_path: str = "") -> str:
    """Open Platform "Signature algorithm" (docs 1366 and 1367).

    Sort every parameter but `sign` by name in ASCII order, join name+value with no separator
    (the official SDK skips blank values), prefix a System Interface's path (never for a `/sync`
    business method), then upper-case hex HMAC-SHA256 keyed with the app secret.
    """
    text = "".join(f"{k}{v}" for k, v in sorted(params.items()) if k != "sign" and v.strip())
    return hmac.new(secret.encode(), (api_path + text).encode(), hashlib.sha256).hexdigest().upper()


def form(
    method: str,
    business: Mapping[str, str],
    *,
    app_key: str,
    secret: str,
    access_token: str,
    timestamp_ms: int,
) -> bytes:
    """Signed form body for `POST https://HOST/sync?method=<method>` (docs 1366, 1369)."""
    params = {
        "app_key": app_key,
        "access_token": access_token,
        "format": "json",
        "method": method,
        "sign_method": "sha256",
        "timestamp": str(timestamp_ms),
        **business,
    }
    return urlencode({**params, "sign": sign(params, secret)}).encode()


def product_params(product_id: str) -> dict[str, str]:
    return {
        "product_id": product_id,
        "ship_to_country": SHIP_TO,
        "target_currency": CURRENCY,
        "target_language": "en",
    }


def freight_params(product_id: str, sku_id: str) -> dict[str, str]:
    query = {
        "quantity": 1,
        "shipToCountry": SHIP_TO,
        "productId": product_id,
        "selectedSkuId": sku_id,
        "language": "en_US",
        "locale": "en_US",
        "currency": CURRENCY,
    }
    return {"queryDeliveryReq": json.dumps(query, separators=(",", ":"))}


def failure(status: int | None, data: Any) -> tuple[Failure, int | None] | None:
    """Gateway errors arrive as `error_response` {type, code, msg, sub_code, sub_msg}."""
    error = data.get("error_response") if isinstance(data, dict) else None
    message = (
        f"{error.get('msg', '')} {error.get('sub_msg', '')}" if isinstance(error, dict) else ""
    )
    if (ban := THROTTLE.search(message)) or status in BLOCK_STATUSES:
        return "blocked", int(ban.group(1)) if ban else None
    if isinstance(error, dict) and error.get("type") == "SYSTEM":
        # "API platform error": authority, permission or signature (Error messages, doc 1372).
        return "revoked", None
    if error is not None or status is None or not 200 <= status < 300:
        return "failed", None
    return None


def _answer(body: bytes, method: str) -> dict[str, Any]:
    data = json.loads(body, parse_float=Decimal)
    answer: dict[str, Any] = data.get(method.replace(".", "_") + "_response", data)
    return answer


def _items(value: Any) -> list[Any]:
    """Unsimplified TOP answers wrap lists as {"<name>_d_t_o": [...]} (docs 1597, 1790)."""
    if isinstance(value, dict):
        (value,) = value.values()
    return value if isinstance(value, list) else []


def parse_product(body: bytes) -> Product | None:
    """None is AliExpress's own "not found / not for sale here" answer (602, 605)."""
    data = _answer(body, PRODUCT)
    if str(data.get("rsp_code")) != "200":
        return None
    result = data["result"]
    base, store = result["ae_item_base_info_dto"], result.get("ae_store_info") or {}
    skus = []
    for sku in _items(result.get("ae_item_sku_info_dtos")):
        if sku["currency_code"] != CURRENCY:
            raise ValueError("AliExpress SKU price is not USD")
        stock = sku.get("sku_available_stock")
        skus.append(
            Sku(
                sku_id=str(sku["sku_id"]),
                price_minor=to_minor(sku["sku_price"], CURRENCY),
                sale_price_minor=to_minor(sku["offer_sale_price"], CURRENCY),
                stock=None if stock is None else int(stock),
            )
        )
    return Product(
        product_id=str(base["product_id"]),
        title=base["subject"],
        rating=base.get("avg_evaluation_rating"),
        review_count=base.get("evaluation_count"),
        sales=base.get("sales_count"),
        store_name=store.get("store_name"),
        skus=skus,
    )


def parse_freight(body: bytes) -> list[Shipping]:
    """An unsuccessful answer (e.g. DELIVERY_NOT_AVAILABLE_TO_YOUR_ADDRESS) means no US option."""
    result = _answer(body, FREIGHT)["result"]
    if result.get("success") is not True:
        return []
    options = []
    for option in _items(result.get("delivery_options")):
        if option["shipping_fee_currency"] != CURRENCY:
            raise ValueError("AliExpress freight fee is not USD")
        # Named "cent", but the documented example is 172.71 for "US $172.71": major units, held
        # to the formatted fee so a cents answer fails instead of costing 100x (DEC-283).
        fee = Decimal(str(option["shipping_fee_cent"]))
        shown = re.search(r"\d[\d,]*(?:\.\d+)?", option.get("shipping_fee_format") or "")
        if shown and Decimal(shown.group().replace(",", "")) != fee:
            raise ValueError("AliExpress freight fee fields disagree")
        options.append(
            Shipping(
                code=option["code"],
                company=option["company"],
                fee_minor=to_minor(fee, CURRENCY),
                free=option["free_shipping"],
                min_days=option.get("min_delivery_days"),
                max_days=option.get("max_delivery_days"),
                ship_from=option.get("ship_from_country"),
            )
        )
    return options
