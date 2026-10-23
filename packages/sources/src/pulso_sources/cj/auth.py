"""CJ authentication responses stay in memory, never in raw captures or logs."""

import json
from collections.abc import Callable
from datetime import UTC, datetime

from pydantic import AwareDatetime, BaseModel, Field, SecretStr

from pulso_core.settings import Settings
from pulso_sources.cj.errors import CJError, classify_error
from pulso_sources.framework import Response


class Tokens(BaseModel):
    access: SecretStr = Field(alias="accessToken")
    access_expires: AwareDatetime = Field(alias="accessTokenExpiryDate")
    refresh: SecretStr = Field(alias="refreshToken")
    refresh_expires: AwareDatetime = Field(alias="refreshTokenExpiryDate")


def parse(body: bytes) -> Tokens:
    response = Response(body, 200)
    if error := classify_error(response):
        raise error
    return Tokens.model_validate(json.loads(body)["data"])


class Auth:
    def __init__(
        self, settings: Settings, *, now: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.settings, self.now = settings, now
        # shortcut: in-process tokens only; add Redis caching in P1-08b before enablement.
        self.tokens: Tokens | None = None

    def token(
        self, post: Callable[[str, dict[str, str]], Response], *, refresh: bool = False
    ) -> str:
        now = self.now()
        if now.utcoffset() is None:
            raise ValueError("CJ auth requires an aware clock")
        tokens = self.tokens
        if tokens and not refresh and now < tokens.access_expires:
            return tokens.access.get_secret_value()
        if tokens and now < tokens.refresh_expires:
            endpoint, body = (
                "refreshAccessToken",
                {"refreshToken": tokens.refresh.get_secret_value()},
            )
        else:
            if self.settings.cj_api_key is None:
                raise CJError("cj_auth_required", "CJ_API_KEY is not configured")
            endpoint, body = (
                "getAccessToken",
                {"apiKey": self.settings.cj_api_key.get_secret_value()},
            )
        response = post(f"/authentication/{endpoint}", body)
        if error := classify_error(response):
            raise error
        tokens = parse(response.body or b"")
        if tokens.access_expires <= self.now() or tokens.refresh_expires <= self.now():
            raise CJError("cj_token_expired", "CJ returned an expired token; no retry")
        self.tokens = tokens
        return tokens.access.get_secret_value()
