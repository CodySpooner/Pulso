from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
    Text,
    Uuid,
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
        Index(None, "source_id", "id"),  # source-filtered run pages (DEC-158)
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
        CheckConstraint("duty_default_bps >= 0", name="duty_default_range"),
        CheckConstraint("returns_bps BETWEEN 0 AND 10000", name="returns_range"),
        CheckConstraint("customs_fee_minor >= 0", name="customs_fee_range"),
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
    # NULL = "duty not set" in the UI, never an assumed 0 (R-16); tariffs can exceed 100%.
    duty_default_bps: Mapped[int | None]
    returns_bps: Mapped[int] = mapped_column(server_default="0")
    customs_fee_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")


class WorkspaceTrackedStore(WorkspaceOwned, Base):
    __tablename__ = "workspace_tracked_stores"
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "store_id"),)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductNote(WorkspaceOwned, CreatedAt, Base):
    __tablename__ = "product_notes"
    __table_args__ = (Index(None, "workspace_id", "product_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProductTag(WorkspaceOwned, Base):
    __tablename__ = "product_tags"
    __table_args__ = (PrimaryKeyConstraint("workspace_id", "product_id", "tag"),)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    tag: Mapped[str] = mapped_column(String(80))


class PopularBrandRule(WorkspaceOwned, CreatedAt, Base):
    """A brand this workspace hides from Google popular, or shows although the major-brand rule
    would hide it (DEC-277). Current preference, not history: replaced and deleted in place."""

    __tablename__ = "popular_brand_rules"
    __table_args__ = (
        PrimaryKeyConstraint("workspace_id", "brand_norm"),
        CheckConstraint("action IN ('hide', 'show')", name="action"),
        CheckConstraint("brand_norm = lower(brand)", name="brand_norm"),  # as DEC-272 b reads
    )
    brand_norm: Mapped[str] = mapped_column(Text)
    brand: Mapped[str] = mapped_column(Text)  # the spelling hidden or shown, for the list
    action: Mapped[str] = mapped_column(String(4))
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))


class ProductKeyword(WorkspaceOwned, CreatedAt, Base):
    """A search keyword the workspace confirmed or rejected for a product (KW-1, DEC-281). A
    later decision sets status, decided_by and decided_at again; a trigger refuses DELETE."""

    __tablename__ = "product_keywords"
    __table_args__ = (
        PrimaryKeyConstraint("workspace_id", "product_id", "keyword"),
        CheckConstraint("status IN ('confirmed', 'rejected')", name="status_values"),
        CheckConstraint("source IN ('title', 'manual')", name="source_values"),
        CheckConstraint("relevance BETWEEN 0 AND 1", name="relevance_range"),
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    keyword: Mapped[str] = mapped_column(String(100))  # normalized: casefolded, spacing collapsed
    relevance: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))  # at decision; null: manual
    source: Mapped[str] = mapped_column(String(20))  # title: a candidate; manual: typed in
    status: Mapped[str] = mapped_column(String(20))
    decided_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


TEST_STAGES = ("idea", "researching", "testing", "winner", "killed")
KILL_REASONS = (  # vault Features/Testing Board
    "no_sales_over_stop_loss",
    "cpa_above_break_even",
    "low_ctr_creatives",
    "supplier_issue",
    "sample_quality",
    "margin_too_thin",
    "saturated",
    "ad_account_rejection",
    "other",
)


def sql_in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(f"'{value}'" for value in values)})"


class ProductTest(WorkspaceOwned, CreatedAt, BigId, Base):
    """A product test on the Testing Board (WF-5, DEC-312). CPA and ROAS are computed on read,
    never stored. start_snapshot is the Profit calc when the test first entered Testing; a
    trigger refuses to change it once taken (R-21)."""

    __tablename__ = "product_tests"
    __table_args__ = (
        Index(
            "uq_product_tests_open",
            "workspace_id",
            "product_id",
            unique=True,
            postgresql_where=text(sql_in("stage", TEST_STAGES[:3])),
        ),
        CheckConstraint(sql_in("stage", TEST_STAGES), name="stage_values"),
        CheckConstraint(sql_in("kill_reason", KILL_REASONS), name="kill_reason_values"),
        CheckConstraint(
            "(stage = 'killed') = (kill_reason IS NOT NULL)", name="kill_reason_killed"
        ),
        CheckConstraint("ended_on >= started_on", name="date_order"),
        CheckConstraint(
            "ad_spend_minor >= 0 AND revenue_minor >= 0 AND orders >= 0", name="metrics_range"
        ),
    )
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"))
    stage: Mapped[str] = mapped_column(String(20), server_default="idea")
    started_on: Mapped[date_type | None]  # UTC calendar dates
    ended_on: Mapped[date_type | None]
    currency: Mapped[str] = mapped_column(
        CHAR(3), ForeignKey("currencies.code"), server_default="USD"
    )
    ad_spend_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    revenue_minor: Mapped[int] = mapped_column(BigInteger, server_default="0")
    orders: Mapped[int] = mapped_column(server_default="0")
    notes: Mapped[str | None] = mapped_column(Text)
    kill_reason: Mapped[str | None] = mapped_column(String(40))
    start_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# The default scenario's landed cost per workspace and product (migration 0010, DEC-265): a
# view, so it sits outside Base.metadata and autogenerate never makes it a table.
workspace_product_economics = Table(
    "workspace_product_economics",
    MetaData(),
    Column("workspace_id", Uuid),
    Column("product_id", Uuid),
    Column("supplier_listing_id", BigInteger),  # null: the product has no supplier listing
    Column("method", Text),  # the freight quote's shipping method
    *(
        Column(name, BigInteger)
        for name in (
            "price_minor",
            "goods_minor",
            "freight_minor",
            "duty_minor",
            "customs_fee_minor",
            "payment_fee_minor",
            "shopify_fee_minor",
            "returns_minor",
            "landed_cost_minor",
            "margin_minor",
            "margin_bps",
            "ad_cost_minor",
            "net_minor",
            "net_bps",
        )
    ),
    Column("complete", Boolean),
    Column("missing", ARRAY(Text)),  # landed_cost.MISSING codes, in that order
    Column("sources", JSONB),  # Calc.sources: {input: {source, as_of, raw_payload_id}}
    Column("as_of", DateTime(timezone=True)),  # the oldest observation in `sources`
)
