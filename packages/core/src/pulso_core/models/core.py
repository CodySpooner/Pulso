from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pulso_core.db import Base, BigId, CreatedAt, Observation, WorkspaceOwned


class Workspace(CreatedAt, Base):
    __tablename__ = "workspaces"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200))


class User(CreatedAt, Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True)


class WorkspaceMember(WorkspaceOwned, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "user_id"),)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(20), server_default="owner")


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    key: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(30))
    enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    status: Mapped[str] = mapped_column(String(20), server_default="disabled")
    disabled_reason: Mapped[str | None] = mapped_column(Text)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_block_count: Mapped[int] = mapped_column(server_default="0")
    last_status_code: Mapped[int | None]
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    phase: Mapped[int] = mapped_column(SmallInteger)


class CollectorRun(BigId, Base):
    __tablename__ = "collector_runs"
    __table_args__ = (
        Index(
            "uq_collector_runs_successful_slot",
            "source_id",
            "slot_key",
            unique=True,
            postgresql_where=text("status = 'success' AND trigger IN ('schedule', 'catchup')"),
        ),
        Index(None, "source_id", "started_at"),
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    trigger: Mapped[str] = mapped_column(String(20))
    slot_key: Mapped[str | None] = mapped_column(String(30))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    host: Mapped[str | None] = mapped_column(String(255))
    git_sha: Mapped[str | None] = mapped_column(String(40))
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), server_default="queued")
    complete: Mapped[bool] = mapped_column(server_default=text("false"))
    rows_fetched: Mapped[int] = mapped_column(BigInteger, server_default="0")
    rows_inserted: Mapped[int] = mapped_column(BigInteger, server_default="0")
    rows_updated: Mapped[int] = mapped_column(BigInteger, server_default="0")
    rows_unchanged: Mapped[int] = mapped_column(BigInteger, server_default="0")
    http_requests: Mapped[int] = mapped_column(server_default="0")
    last_status_code: Mapped[int | None]
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)


class RawPayload(BigId, Base):
    __tablename__ = "raw_payloads"
    __table_args__ = (
        Index(None, "source_id", "captured_at"),
        Index(
            "uq_raw_payloads_import",
            "source_id",
            "sha256",
            "template_version",
            unique=True,
            postgresql_where=text("template_version IS NOT NULL"),
        ),
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), index=True)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    request: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status_code: Mapped[int | None]
    content_type: Mapped[str | None] = mapped_column(String(200))
    etag: Mapped[str | None] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    template_version: Mapped[str | None] = mapped_column(String(80))
    storage_key: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Currency(Base):
    __tablename__ = "currencies"
    __table_args__ = (CheckConstraint("exponent BETWEEN 0 AND 3", name="exponent_range"),)
    code: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    exponent: Mapped[int] = mapped_column(SmallInteger)


class FxRate(Observation, Base):
    __tablename__ = "fx_rates"
    observation_keys = ("date", "base", "quote", "source")
    date: Mapped[date_type] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), primary_key=True)
    quote: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), primary_key=True)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8))


class WorkspaceSettings(WorkspaceOwned, Base):
    __tablename__ = "settings"
    __table_args__ = (
        PrimaryKeyConstraint("workspace_id"),
        CheckConstraint("default_country = 'US' AND currency = 'USD'", name="v1_market"),
        CheckConstraint("payment_fee_bps BETWEEN 0 AND 10000", name="payment_fee_range"),
        CheckConstraint("shopify_fee_bps BETWEEN 0 AND 10000", name="shopify_fee_range"),
        CheckConstraint("target_margin_bps BETWEEN 0 AND 10000", name="target_margin_range"),
        CheckConstraint(
            "payment_fee_fixed_minor >= 0 AND default_cpa_minor >= 0", name="cost_range"
        ),
    )
    default_country: Mapped[str] = mapped_column(CHAR(2), server_default="US")
    currency: Mapped[str] = mapped_column(
        CHAR(3), ForeignKey("currencies.code"), server_default="USD"
    )
    payment_fee_bps: Mapped[int] = mapped_column(server_default="0")
    payment_fee_fixed_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    shopify_fee_bps: Mapped[int] = mapped_column(server_default="0")
    default_cpa_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    target_margin_bps: Mapped[int] = mapped_column(server_default="0")


class WorkspaceTrackedStore(WorkspaceOwned, Base):
    __tablename__ = "workspace_tracked_stores"
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "store_id"),)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
