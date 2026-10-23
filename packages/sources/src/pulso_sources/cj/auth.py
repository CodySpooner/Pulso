"""CJ tokens live in memory/Redis, never in raw captures or logs."""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pydantic import AwareDatetime, BaseModel, Field, SecretStr
from redis import Redis

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
        self,
        settings: Settings,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        cache: Redis | None = None,
    ) -> None:
        self.settings, self.now, self.cache = settings, now, cache
        key = settings.cj_api_key.get_secret_value() if settings.cj_api_key else ""
        self.cache_key = "pulso:cj:auth:" + hashlib.sha256(key.encode()).hexdigest()
        self.tokens: Tokens | None = None

    def token(
        self, post: Callable[[str, dict[str, str]], Response], *, refresh: bool = False
    ) -> str:
        now = self.now()
        if now.utcoffset() is None:
            raise ValueError("CJ auth requires an aware clock")
        if self.tokens is None and self.cache is not None:
            cached = self.cache.get(self.cache_key)
            if isinstance(cached, (str, bytes)):
                self.tokens = Tokens.model_validate_json(cached)
        tokens = self.tokens
        safe_until = now + timedelta(minutes=5)
        if tokens and not refresh and safe_until < tokens.access_expires:
            return tokens.access.get_secret_value()
        if tokens and safe_until < tokens.refresh_expires:
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
        safe_until = self.now() + timedelta(minutes=5)
        if tokens.access_expires <= safe_until or tokens.refresh_expires <= safe_until:
            raise CJError("cj_token_expired", "CJ returned an expired token; no retry")
        self.tokens = tokens
        if self.cache is not None:
            data = tokens.model_dump(mode="json", by_alias=True)
            data.update(
                accessToken=tokens.access.get_secret_value(),
                refreshToken=tokens.refresh.get_secret_value(),
            )
            self.cache.set(
                self.cache_key,
                json.dumps(data),
                ex=int((tokens.refresh_expires - safe_until).total_seconds()),
            )
        return tokens.access.get_secret_value()
