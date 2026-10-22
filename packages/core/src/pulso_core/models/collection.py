"""Global collection evidence and operations; no workspace-owned state."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
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
    __table_args__ = (Index(None, "host", "at"),)
    host: Mapped[str] = mapped_column(String(255))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CollectionGap(BigId, Base):
    __tablename__ = "collection_gaps"
    __table_args__ = (
        UniqueConstraint("source_id", "slot_key"),
        CheckConstraint("slot_end > slot_start", name="slot_range"),
        Index(None, "source_id", "slot_start"),
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
