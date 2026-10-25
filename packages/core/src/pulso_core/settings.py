"""Typed, env-driven settings shared by the API and the workers.

Sources, highest priority first: process env vars, `.env.local` (per-worktree, written by
infra/scripts/worktree_env.py), `.env`. Every variable is documented in `.env.example`.
"""

import re
from functools import lru_cache
from typing import Annotated, Literal, Self

from pydantic import (
    Field,
    HttpUrl,
    NonNegativeInt,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# A list read from a comma-separated env value ("a, b") instead of JSON.
CommaList = Annotated[list[str], NoDecode]
# Two or more labels; the last starts with a letter, so an IPv4 literal never matches.
DNS_NAME = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_ignore_empty=True,  # `DATABASE_URL=` copied from .env.example counts as missing
        extra="ignore",  # .env also holds compose-only and web-only variables
    )

    database_url: SecretStr
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    # S3-compatible object storage: RustFS locally, Cloudflare R2 in production.
    s3_endpoint_url: str = "http://localhost:9000"
    s3_region: str = "us-east-1"
    s3_bucket_raw: str = "pulso-raw"
    s3_access_key_id: str
    s3_secret_access_key: SecretStr

    # Clerk JWT verification (API only; workers leave these unset).
    clerk_issuer: str | None = None
    clerk_jwks_url: str | None = None
    clerk_authorized_parties: CommaList = []
    platform_admin_user_ids: CommaList = []

    # Only the collector host turns these on (DEC-002). Accepts on/off, true/false, 1/0.
    pulso_scheduler: bool = False
    collectors_live: bool = False

    pulso_bot_contact: HttpUrl | None = None
    collector_block_threshold: PositiveInt = 5
    collector_max_retries: NonNegativeInt = 3
    collector_backoff_base_seconds: PositiveInt = 2
    collector_backoff_cap_seconds: PositiveInt = 30
    collector_retry_wait_cap_seconds: Annotated[int, Field(ge=0, le=600)] = 600
    collector_wall_time_seconds: PositiveInt = 45 * 60
    collect_soft_time_limit_seconds: PositiveInt = 60 * 60
    collect_hard_time_limit_seconds: PositiveInt = 75 * 60
    collector_task_max_retries: NonNegativeInt = 2
    collector_task_retry_seconds: PositiveInt = 15 * 60
    collector_request_timeout_seconds: PositiveInt = 30
    shopify_requests_per_minute: Annotated[int, Field(gt=0, le=30)] = 30
    shopify_js_panel_size: Annotated[int, Field(gt=0, le=20)] = 10
    shopify_wall_time_seconds: PositiveInt = 30 * 60
    cj_api_key: SecretStr | None = None
    cj_requests_per_second: Annotated[float, Field(gt=0, le=1)] = 1
    cj_daily_points_budget: Annotated[int, Field(gt=0, le=20000)] = 20000
    cj_wall_time_seconds: PositiveInt = 30 * 60
    serpapi_api_key: SecretStr | None = None
    trends_monthly_search_limit: Annotated[int, Field(ge=0, le=250)] = 250
    trends_hourly_search_limit: Annotated[int, Field(ge=1, le=50)] = 50
    trends_wall_time_seconds: PositiveInt = 10 * 60
    fx_wall_time_seconds: PositiveInt = 5 * 60
    # Listing images (DEC-240): only these exact https hosts, each checked before it is listed.
    image_hosts: CommaList = []
    image_requests_per_minute: Annotated[int, Field(gt=0, le=30)] = 30  # per host

    @model_validator(mode="after")
    def _collector_limits(self) -> Self:
        budgets = (
            self.collector_wall_time_seconds,
            self.shopify_wall_time_seconds,
            self.cj_wall_time_seconds,
            self.trends_wall_time_seconds,
            self.fx_wall_time_seconds,
        )
        if (
            not max(budgets)
            < self.collect_soft_time_limit_seconds
            < self.collect_hard_time_limit_seconds
        ):
            raise ValueError("Collector budgets must be below soft limit, then hard limit")
        if self.collector_backoff_base_seconds > self.collector_backoff_cap_seconds:
            raise ValueError("Collector backoff base must not exceed cap")
        return self

    @property
    def collector_user_agent(self) -> str:
        if self.pulso_bot_contact is None:
            raise ValueError("PULSO_BOT_CONTACT is required for live collection")
        return f"PulsoBot/0.1 (+{self.pulso_bot_contact})"  # DEC-073

    api_port: int = 8000
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    @field_validator(
        "clerk_authorized_parties", "platform_admin_user_ids", "image_hosts", mode="before"
    )
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("image_hosts")
    @classmethod
    def _bare_hosts(cls, value: list[str]) -> list[str]:
        # No scheme, port, userinfo, path, IP literal or upper case: such an entry matches no URL.
        if not all(DNS_NAME.fullmatch(host) for host in value):
            raise ValueError("IMAGE_HOSTS entries must be bare lowercase DNS names")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
