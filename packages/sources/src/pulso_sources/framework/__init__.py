"""Public collection contract. Lifecycle helpers own commits on a dedicated Session."""

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, RawPayload, Source
from pulso_core.settings import Settings
from pulso_core.worktree import is_linked_worktree
from pulso_sources.storage import JsonValue


class CollectorsLiveDisabled(RuntimeError):
    pass


@dataclass(frozen=True)
class Request:
    params: dict[str, JsonValue] = field(default_factory=dict)
    mode: Literal["live", "fixture", "csv", "json"] = "live"
    body: bytes | None = None
    content_type: str | None = "application/json"
    raw_payload_id: int | None = None


@dataclass(frozen=True)
class Response:
    body: bytes | None
    status_code: int | None = None
    content_type: str | None = "application/json"
    etag: str | None = None
    complete: bool = True
    headers: Mapping[str, str] = field(default_factory=dict)


type RequestHook = Callable[[Session, Source, CollectorRun, Request, Response | None], None]


@dataclass(frozen=True)
class Target:
    scope: str
    target_id: str
    requests: Iterable[Request]


@dataclass(frozen=True)
class UpsertStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


class Adapter[R](Protocol):
    @property
    def parser_version(self) -> str: ...
    def fetch(self, request: Request, *, user_agent: str) -> Response: ...
    def parse(self, body: bytes) -> Sequence[R]: ...
    def upsert(
        self, session: Session, records: Sequence[R], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats: ...


def fetch[R](adapter: Adapter[R], request: Request, *, settings: Settings) -> Response:
    """Only this boundary calls adapter HTTP; offline inputs never call adapter.fetch."""
    if request.raw_payload_id is not None and request.mode == "live":
        raise ValueError("Existing raw captures require an offline request")
    if request.mode in {"fixture", "csv", "json"}:
        return Response(request.body, content_type=request.content_type)
    if request.mode != "live" or not settings.collectors_live or is_linked_worktree(__file__):
        raise CollectorsLiveDisabled(
            "Live collection requires COLLECTORS_LIVE=on outside worktrees"
        )
    return adapter.fetch(request, user_agent=settings.collector_user_agent)


def slot_key(job: str, at: datetime, *, cadence: Literal["daily", "weekly"] = "daily") -> str:
    if at.utcoffset() is None or not re.fullmatch(r"[a-z][a-z0-9_]*", job):
        raise ValueError("Slot requires an aware timestamp and a lowercase job name")
    at = at.astimezone(UTC)
    period = at.strftime("%Y-%m-%d" if cadence == "daily" else "%G-W%V")
    value = f"{job}:{period}"
    if cadence not in {"daily", "weekly"} or len(value) > 30:
        raise ValueError("Invalid cadence or slot exceeds 30 characters")
    return value


# Imported last because lifecycle uses the public protocol/value types above.
from pulso_sources.framework.lifecycle import RunDeferred, enqueue_run, execute_run  # noqa: E402
from pulso_sources.framework.observations import (  # noqa: E402
    Writer,
    append_observation,
    current_fields,
    effective_observation,
)

__all__ = [
    "Adapter",
    "CollectorsLiveDisabled",
    "Request",
    "RequestHook",
    "Response",
    "RunDeferred",
    "Target",
    "UpsertStats",
    "Writer",
    "append_observation",
    "current_fields",
    "effective_observation",
    "enqueue_run",
    "execute_run",
    "fetch",
    "slot_key",
]
