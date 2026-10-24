"""Data Health admin shapes (DH-1). Null means unknown: the UI shows "no source yet", never 0."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from pulso_sources.cj.activity import Evidence, Utc


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
    blocked_by: int | None = Field(
        description="The active run that suppressed this skipped slot (DEC-108); null otherwise."
    )
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
    next_cursor: str | None = Field(description="Pass as `cursor` for the next target page.")


class RunPage(BaseModel):
    items: list[Run]
    next_cursor: int | None = Field(description="Pass as `cursor` for the next (older) page.")


class CJActivity(BaseModel):
    """DEC-216: missing or invalid stored evidence is unknown, with every other field null."""

    state: Literal["unknown", "ok", "warn", "expired"]
    days_remaining: int | None = Field(
        description="30 minus UTC days since the transaction; 0 or less once expired."
    )
    as_of: datetime | None = Field(description="The evidence's transaction time.")
    observed_at: datetime | None


def not_future(value: datetime) -> datetime:
    if value > datetime.now(UTC):
        raise ValueError("Evidence cannot be observed in the future")
    return value


class ActivityEntry(Evidence):
    """The owner's latest positive CJ transaction; Evidence's checks apply (DEC-216)."""

    kind: Literal["owner_entry"] = "owner_entry"
    observed_at: Annotated[Utc, AfterValidator(not_future)] = Field(
        default_factory=lambda: datetime.now(UTC), description="Defaults to the server's UTC now."
    )
    currency: str = Field("USD", pattern=r"^[A-Z]{3}$")


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
    csv_import: Literal["ready", "preview_only"] | None = Field(
        description="Null: no CSV template. preview_only: commit waits for its import adapter."
    )
    activity: CJActivity | None = Field(
        None, exclude_if=lambda value: value is None, description="CJ only; other sources omit it."
    )


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
    next_cursor: str | None = Field(description="Pass as `cursor` for the next (older) gap page.")
    latest_gap_ends: dict[str, datetime] = Field(
        description="Latest unfilled gap end per source across the entire 90-day window."
    )


class RowError(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    row: int
    column: str
    message: str


class ImportPreview(BaseModel):
    rows: list[dict[str, bool | int | Decimal | date | str]] = Field(
        description="First 20 valid rows; nothing is written."
    )
    valid: int
    invalid: int
    skipped: int = Field(description="Blank lines.")
    error_count: int
    errors: list[RowError] = Field(description="First 100 row errors.")


class ImportResult(BaseModel):
    run: Run
    raw_payload_id: int | None
    original_run_id: int | None = Field(description="Set when a repeat upload was skipped.")
    in_progress: bool = Field(description="Skipped because original_run_id is still importing.")
    error_count: int
    errors: list[RowError] = Field(description="First 100 row errors.")
