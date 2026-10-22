"""Typed, env-driven settings shared by the API and the workers.

Sources, highest priority first: process env vars, `.env.local` (per-worktree, written by
infra/scripts/worktree_env.py), `.env`. Every variable is documented in `.env.example`.
"""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# A list read from a comma-separated env value ("a, b") instead of JSON.
CommaList = Annotated[list[str], NoDecode]


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

    api_port: int = 8000
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    @field_validator("clerk_authorized_parties", "platform_admin_user_ids", mode="before")
    @classmethod
    def _split_commas(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
