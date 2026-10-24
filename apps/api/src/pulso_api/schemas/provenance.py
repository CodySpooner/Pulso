"""The provenance contract (Q-1, DEC-238): every number a resource returns names its source."""

from pydantic import AwareDatetime, BaseModel


class Sourced(BaseModel):
    """A number traced to the newest observation it uses."""

    value: int
    source: str  # sources.key of that observation, e.g. "shopify_stores"
    source_name: str
    as_of: AwareDatetime  # its captured_at (UTC)
    raw_payload_id: int | None
    method: str | None = None  # set only on Pulso's own estimates
    stale: bool  # as_of is older than twice the source's expected interval


class NoSource(BaseModel):
    """A number nothing backs yet: null with the reason, never 0 (DEC-040)."""

    value: None
    reason: str


Stat = Sourced | NoSource
