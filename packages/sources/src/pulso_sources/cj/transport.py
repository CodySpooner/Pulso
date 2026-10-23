"""Sequential CJ HTTP; the collector owns attempt accounting and raw retry evidence."""

import json
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from http.client import HTTPException, HTTPSConnection
from typing import Annotated, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, StrictInt
from redis import Redis

from pulso_core.settings import Settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.errors import CJError, classify_error
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response
from pulso_sources.storage import JsonValue

_next_request = 0.0
ENDPOINTS = {
    "/product/listV2",
    "/product/getCategory",
    "/product/query",
    "/product/stock/getInventoryByPid",
    "/logistic/freightCalculate",
}


class FreightProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vid: Annotated[str, Field(min_length=1, max_length=200)]
    quantity: Annotated[StrictInt, Field(ge=1, le=1)]


class FreightRequest(BaseModel):
    startCountryCode: Literal["CN", "US"]
    endCountryCode: Literal["US"]
    products: Annotated[list[FreightProduct], Field(min_length=1, max_length=1)]


class ProductRequest(BaseModel):
    pid: Annotated[str, Field(min_length=1, max_length=200)]


class Transport:
    def __init__(
        self,
        settings: Settings,
        before_send: Callable[[str], None],
        rejected: Callable[[Request, Response], None],
        received: Callable[[Response], None] | None = None,
    ) -> None:
        self.settings, self.before_send, self.rejected = settings, before_send, rejected
        self.received = received
        self.auth = Auth(
            settings,
            cache=Redis.from_url(
                settings.redis_url.get_secret_value(),
                socket_timeout=settings.collector_request_timeout_seconds,
                socket_connect_timeout=settings.collector_request_timeout_seconds,
            ),
        )
        self.deadline = time.monotonic() + settings.cj_wall_time_seconds
        self.sent = 0
        self.error: CJError | None = None
        self.auth_failure: Response | None = None

    def guard(self, request: Request) -> None:
        if not self.settings.collectors_live or is_linked_worktree(__file__):
            raise CollectorsLiveDisabled(
                "CJ live collection requires enabled flags outside worktrees"
            )
        if request.params.get("endpoint") not in ENDPOINTS:
            raise ValueError("Unsupported CJ read endpoint")
        if request.params["endpoint"] == "/logistic/freightCalculate":
            FreightRequest.model_validate(request.params)
        if request.params["endpoint"] in {"/product/query", "/product/stock/getInventoryByPid"}:
            ProductRequest.model_validate(request.params)
        _ = self.settings.collector_user_agent  # Validate contact before auth or reservations.

    def send(
        self, endpoint: str, params: Mapping[str, JsonValue], *, token: str | None = None
    ) -> Response:
        global _next_request
        wait = max(0, _next_request - time.monotonic())
        if time.monotonic() + wait >= self.deadline:
            raise CJError("cj_wall_time_budget", "CJ wall-time budget reached")
        if wait:
            time.sleep(wait)
        self.before_send(endpoint)
        self.sent += 1
        _next_request = time.monotonic() + 1 / self.settings.cj_requests_per_second
        response = self.http(endpoint, params, token=token)
        if self.received is not None:
            self.received(response)
        if token is None and classify_error(response):
            self.auth_failure = Response(None, response.status_code, headers=response.headers)
        return response

    def http(
        self, endpoint: str, params: Mapping[str, JsonValue], *, token: str | None
    ) -> Response:
        headers = {
            "User-Agent": self.settings.collector_user_agent,
            "Content-Type": "application/json",
        }
        if token is not None:
            headers["CJ-Access-Token"] = token
        path = "/api2.0/v1" + endpoint
        post = token is None or endpoint == "/logistic/freightCalculate"
        try:
            with closing(
                HTTPSConnection(
                    "developers.cjdropshipping.com",
                    timeout=self.settings.collector_request_timeout_seconds,
                )
            ) as connection:
                connection.request(
                    "POST" if post else "GET",
                    path + ("?" + urlencode(params) if not post and params else ""),
                    body=json.dumps(params) if post else None,
                    headers=headers,
                )
                with closing(connection.getresponse()) as response:
                    return Response(
                        response.read(),
                        response.status,
                        response.getheader("Content-Type"),
                        headers=dict(response.getheaders()),
                    )
        except OSError, HTTPException:
            raise ConnectionError("CJ transport failed") from None

    def fetch(self, request: Request) -> Response:
        self.guard(request)
        endpoint = str(request.params["endpoint"])
        params = {k: v for k, v in request.params.items() if k != "endpoint"}
        try:
            token = self.auth.token(self.send)
            response = self.send(endpoint, params, token=token)
            failure = classify_error(response)
            if (
                failure
                and failure.code == "cj_token_expired"
                and response.status_code in {200, 401}
                and not any(k.lower() == "retry-after" for k in response.headers)
            ):
                self.rejected(request, response)
                token = self.auth.token(self.send, refresh=True)
                response = self.send(endpoint, params, token=token)
            return response
        except CJError as error:
            self.error = error
            raise
