"""Data Health admin shapes (DH-1). Null means unknown: the UI shows "no source yet", never 0."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Run(BaseModel):
    id: int
    source_key: str
    trigger: str
    slot_key: str | None
    status: str
    complete: bool
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    rows_fetched: int
    rows_inserted: int
    rows_updated: int
    rows_unchanged: int
    http_requests: int
    last_status_code: int | None
    error_code: str | None
    error_message: str | None
    host: str | None
    target_count: int
    successful_target_count: int


class RunTarget(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scope: str
    target_id: str
    status: str
    raw_payload_id: int | None
    captured_at: datetime


class RunDetail(Run):
    targets: list[RunTarget]


class RunPage(BaseModel):
    items: list[Run]
    next_cursor: int | None = Field(description="Pass as `cursor` for the next (older) page.")


class SourceHealth(BaseModel):
    key: str
    name: str
    type: str
    phase: int
    enabled: bool
    status: str
    disabled_reason: str | None
    disabled_at: datetime | None
    retry_not_before: datetime | None
    last_status_code: int | None
    last_run: Run | None
    freshness: datetime | None = Field(
        description="Last successful target observation, including unchanged/304 (R-06)."
    )
    seed_approved: bool | None = Field(description="Null when the source has no seed list.")
    approved_targets: int | None
    quota_used: int | None = Field(None, description="Null until quota usage is persisted.")
    quota_limit: int | None = None


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    reason: str | None = Field(None, max_length=1000)


class CoverageDay(BaseModel):
    source_key: str
    day: date
    status: Literal["success", "partial", "gap", "running", "queued", "failed", "filled", "unknown"]
    runs: int
    rows: int
    targets: int
    successful_targets: int


class Heartbeat(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    host: str
    at: datetime


class Gap(BaseModel):
    source_key: str
    slot_key: str
    slot_start: datetime
    slot_end: datetime
    reason: str
    detected_at: datetime


class HostHealth(BaseModel):
    live_runs_allowed: bool = Field(description="False: Run now answers 409 (D2).")
    latest_heartbeat: Heartbeat | None
    open_gaps: list[Gap] = Field(description="Unfilled gaps starting in the last 90 days.")
