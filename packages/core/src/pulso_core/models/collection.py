"""Global collection evidence and operations; no workspace-owned state."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pulso_core.db import Base, BigId, Observation


class SearchTrend(Observation, BigId, Base):
    __tablename__ = "search_trends"
    observation_keys = (
        "source_id",
        "keyword",
        "geo",
        "window",
        "granularity",
        "observed_for",
        "metric",
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    keyword: Mapped[str] = mapped_column(Text)
    geo: Mapped[str] = mapped_column(CHAR(2))
    window: Mapped[str] = mapped_column(String(80))
    granularity: Mapped[str] = mapped_column(String(20))
    metric: Mapped[str] = mapped_column(String(80))
    value: Mapped[Decimal] = mapped_column(Numeric)
    is_partial: Mapped[bool] = mapped_column(server_default=text("false"))


Index(
    "ix_search_trends_keyword_geo_captured_at",
    SearchTrend.keyword,
    SearchTrend.geo,
    SearchTrend.captured_at,
)


class PopularProduct(Observation, BigId, Base):
    """One ranked row of the owner's weekly Merchant Center Popular products download (DEC-267).

    Google's terms allow internal use only: never show these rows on a public page.
    observed_for is the Monday that starts the report week (Google's `W20261012`).
    """

    __tablename__ = "popular_products"
    observation_keys = ("source_id", "country", "category", "observed_for", "rank")
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    country: Mapped[str] = mapped_column(CHAR(2))
    category: Mapped[str | None] = mapped_column(Text)
    rank: Mapped[int]
    previous_rank: Mapped[int | None]
    title: Mapped[str] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    availability: Mapped[str | None] = mapped_column(Text)
    relative_demand: Mapped[str | None] = mapped_column(Text)
    relative_demand_change: Mapped[str | None] = mapped_column(Text)
    # As Google wrote them; products resolve on read through M-4's normaliser (DEC-267 c).
    gtins: Mapped[str | None] = mapped_column(Text)
    price_min_minor: Mapped[int | None] = mapped_column(BigInteger)
    price_max_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str | None] = mapped_column(CHAR(3), ForeignKey("currencies.code"))


class CollectorRunTarget(Base):
    __tablename__ = "collector_run_targets"
    __table_args__ = (
        Index(None, "scope", "target_id", "captured_at"),
        CheckConstraint(
            "status <> 'success' OR raw_payload_id IS NOT NULL", name="success_evidence"
        ),
    )
    run_id: Mapped[int] = mapped_column(ForeignKey("collector_runs.id"), primary_key=True)
    scope: Mapped[str] = mapped_column(String(30), primary_key=True)
    target_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    raw_payload_id: Mapped[int | None] = mapped_column(ForeignKey("raw_payloads.id"))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class HostHeartbeat(BigId, Base):
    __tablename__ = "host_heartbeats"
    __table_args__ = (Index(None, "host", "at"), Index(None, "at"))
    host: Mapped[str] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CollectionGap(BigId, Base):
    __tablename__ = "collection_gaps"
    __table_args__ = (
        UniqueConstraint("source_id", "slot_key"),
        CheckConstraint("slot_end > slot_start", name="slot_range"),
        Index(None, "source_id", "slot_start"),
        Index(
            "ix_collection_gaps_open_slot_start",
            "slot_start",
            postgresql_where=text("filled_by_run_id IS NULL"),
        ),
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    slot_key: Mapped[str] = mapped_column(String(30))
    slot_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    slot_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(30))
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    filled_by_run_id: Mapped[int | None] = mapped_column(ForeignKey("collector_runs.id"))


class SourceEvent(BigId, Base):
    __tablename__ = "source_events"
    __table_args__ = (Index(None, "source_id", "at"),)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    actor: Mapped[str] = mapped_column(String(255), server_default="system")
    action: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
