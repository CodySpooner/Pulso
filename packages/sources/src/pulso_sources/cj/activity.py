"""CJ disables the API after 30 days with zero transaction amount (`1600014`).

Activity comes only from explicit evidence of the account's latest positive transaction.
Token issuance, auth responses and API-created orders never establish it.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    model_validator,
)

WINDOW_DAYS = 30
WARN_DAYS = 7

Utc = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]


class Evidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["owner_entry", "csv_export"]
    transaction_at: Utc
    observed_at: Utc
    amount_minor: Annotated[StrictInt, Field(gt=0)]
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def observed_after_transaction(self) -> Evidence:
        if self.transaction_at > self.observed_at:
            raise ValueError("CJ transaction cannot be after its observation")
        return self


@dataclass(frozen=True)
class Status:
    state: Literal["unknown", "ok", "warn", "expired"]
    days_remaining: int | None


def countdown(evidence: Evidence | None, now: datetime) -> Status:
    """Count UTC dates, so expiry never trails 30 full days; CJ's own day boundary is unverified.

    Stale evidence only shortens the countdown: a later transaction can only extend it.
    """
    if now.utcoffset() is None:
        raise ValueError("CJ activity requires an aware UTC clock")
    if evidence is None or evidence.observed_at > now:
        return Status("unknown", None)
    days = WINDOW_DAYS - (now.astimezone(UTC).date() - evidence.transaction_at.date()).days
    return Status("expired" if days <= 0 else "warn" if days <= WARN_DAYS else "ok", days)
