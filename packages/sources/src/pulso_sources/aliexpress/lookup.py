"""AE-2 live lookup: Redis answers for 24 h, AliExpress only on a miss, nothing durable.

DEC-037: no raw_payloads row, S3 object, snapshot, observation, feature or payload log line.
The only database writes are the shared source block state (DEC-283).
"""

import json
import re
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime, timedelta
from http.client import HTTPException, HTTPSConnection
from typing import Literal
from urllib.parse import urlencode

from pydantic import AwareDatetime, BaseModel
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Source, SourceEvent
from pulso_core.settings import Settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.aliexpress import (
    FREIGHT,
    HOST,
    PRODUCT,
    SHIP_TO,
    Failure,
    Product,
    Shipping,
    failure,
    form,
    freight_params,
    parse_freight,
    parse_product,
    product_params,
)
from pulso_sources.framework import CollectorsLiveDisabled, Response
from pulso_sources.framework.lifecycle import _retry_after

TTL_SECONDS = 24 * 60 * 60
DAILY_CALL_CAP = 500  # ponytail: a constant below the lowest reported new-app limit (vault note)

type Transport = Callable[[str, bytes], Response]
type Status = Literal["ok", "not_found", "disabled", "not_configured", "throttled", "error"]


class Answer(BaseModel):
    status: Status
    product: Product | None = None
    shipping: list[Shipping] | None = None  # None: no SKU asked; []: no option to the US
    as_of: AwareDatetime | None = None


class _Stop(Exception):
    def __init__(self, status: Status) -> None:
        self.status = status


def cache_key(product_id: str, sku_id: str | None) -> str:
    return f"pulso:aliexpress:v1:{product_id}:{sku_id or '-'}:{SHIP_TO}"


def https_transport(settings: Settings) -> Transport:
    if not settings.collectors_live or is_linked_worktree(__file__):
        raise CollectorsLiveDisabled("AliExpress live lookup requires COLLECTORS_LIVE=on")
    user_agent = settings.collector_user_agent  # Fails before any call without a contact URL.

    def send(method: str, body: bytes) -> Response:
        try:
            with closing(
                HTTPSConnection(HOST, timeout=settings.collector_request_timeout_seconds)
            ) as connection:
                connection.request(
                    "POST",
                    "/sync?" + urlencode({"method": method}),
                    body=body,
                    headers={
                        "User-Agent": user_agent,
                        "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
                        "Accept": "application/json",
                    },
                )
                with closing(connection.getresponse()) as response:
                    return Response(
                        response.read(),
                        response.status,
                        response.getheader("Content-Type"),
                        headers=dict(response.getheaders()),
                    )
        except OSError, HTTPException:
            raise ConnectionError("AliExpress transport failed") from None

    return send


def _block(
    session: Session,
    source: Source,
    settings: Settings,
    response: Response,
    kind: Failure,
    ban_seconds: int | None,
    at: datetime,
) -> None:
    """The shared source block state, as the collector lifecycle and CJ record it."""
    session.refresh(source, with_for_update=True)  # An owner may have changed it mid-call.
    source.last_status_code = response.status_code
    if kind == "blocked":
        source.consecutive_block_count += 1
        retry_at = _retry_after(response, at) or (
            at + timedelta(seconds=ban_seconds) if ban_seconds else None
        )
        if retry_at is not None:
            source.retry_not_before = max(source.retry_not_before or retry_at, retry_at)
    if source.enabled and (
        kind == "revoked" or source.consecutive_block_count >= settings.collector_block_threshold
    ):
        reason = (
            "aliexpress_auth_rejected" if kind == "revoked" else "consecutive_blocks:aliexpress"
        )
        source.enabled, source.status = False, "blocked"
        source.disabled_at, source.disabled_reason = at, reason
        session.add(
            SourceEvent(source_id=source.id, actor="system", action="disable", reason=reason, at=at)
        )
    session.commit()


def lookup(
    session: Session,
    cache: Redis,
    product_id: str,
    sku_id: str | None = None,
    *,
    settings: Settings,
    transport: Transport | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> Answer:
    """Product detail (and the SKU's US freight when asked), shipped to the US, in USD."""
    if not all(re.fullmatch(r"[0-9]{1,30}", v) for v in (product_id, sku_id or "0")):
        raise ValueError("AliExpress product and SKU IDs are digits")
    if not settings.aliexpress_enabled:
        return Answer(status="disabled")
    key = cache_key(product_id, sku_id)
    if isinstance(cached := cache.get(key), (str, bytes)):
        return Answer.model_validate_json(cached)
    app_key, secret = settings.aliexpress_app_key, settings.aliexpress_app_secret
    token = settings.aliexpress_access_token
    if not (app_key and secret and token):
        return Answer(status="not_configured")
    source = session.scalar(select(Source).filter_by(key="aliexpress"))
    at = now()
    if source is None or not source.enabled:
        return Answer(status="disabled")
    if source.retry_not_before is not None and source.retry_not_before > at:
        return Answer(status="throttled")
    try:
        send = transport or https_transport(settings)
    except CollectorsLiveDisabled:
        return Answer(status="disabled")

    def call(method: str, business: dict[str, str]) -> bytes:
        session.refresh(source)  # The owner or another lookup may have changed it (XR-46).
        if not source.enabled:
            raise _Stop("disabled")
        if source.retry_not_before is not None and source.retry_not_before > now():
            raise _Stop("throttled")
        session.commit()  # Nothing stays open across the HTTPS call (DEC-099).
        calls = f"pulso:aliexpress:calls:{at.date().isoformat()}"
        used = cache.incr(calls)  # Counted before the call, never refunded.
        cache.expire(calls, 2 * TTL_SECONDS)
        if not isinstance(used, int) or used > DAILY_CALL_CAP:
            raise _Stop("throttled")
        body = form(
            method,
            business,
            app_key=app_key,
            secret=secret.get_secret_value(),
            access_token=token.get_secret_value(),
            timestamp_ms=int(at.timestamp() * 1000),
        )
        try:
            response = send(method, body)
        except TimeoutError, ConnectionError:
            raise _Stop("error") from None
        try:
            data = json.loads(response.body or b"null")
        except ValueError:
            data = None
        found = failure(response.status_code, data)
        if found is None:
            if source.consecutive_block_count:
                session.refresh(source, with_for_update=True)
                source.consecutive_block_count = 0
                session.commit()
            return response.body or b""
        kind, ban_seconds = found
        if kind == "failed":
            raise _Stop("error")
        _block(session, source, settings, response, kind, ban_seconds, now())  # answered (XR-45)
        raise _Stop("throttled" if source.enabled else "disabled")

    try:
        product = parse_product(call(PRODUCT, product_params(product_id)))
        if product is None:
            answer = Answer(status="not_found", as_of=at)
        else:
            shipping = (
                None
                if sku_id is None
                else parse_freight(call(FREIGHT, freight_params(product_id, sku_id)))
            )
            answer = Answer(status="ok", product=product, shipping=shipping, as_of=at)
    except _Stop as stop:
        return Answer(status=stop.status)
    except ValueError, KeyError, TypeError:
        return Answer(status="error")  # Malformed answer: nothing cached, nothing logged.
    cache.set(key, answer.model_dump_json(), ex=TTL_SECONDS)
    return answer
