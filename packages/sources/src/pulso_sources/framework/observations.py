"""Append observations; FX's first-rate rule remains adapter-owned (DEC-060)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import (
    ListingSnapshot,
    RawPayload,
    SearchTrend,
    ShippingOption,
    VariantSnapshot,
)

type ObservationRow = ListingSnapshot | VariantSnapshot | ShippingOption | SearchTrend


@dataclass(frozen=True, eq=False)
class Writer:
    """One evidence kind sharing a model: its captures' request predicate and owned fields."""

    captures: ColumnElement[bool]
    fields: tuple[str, ...]


def effective_observation[T: ObservationRow](
    session: Session,
    model: type[T],
    *,
    key: dict[str, Any],
    raw_payload_id: int | None = None,
    before: tuple[date, datetime, int] | None = None,
    writer: Writer | None = None,
    captured_before: datetime | None = None,
) -> T | None:
    """Latest observed day/capture, or greatest id in one capture; both bounds are exclusive."""
    if set(key) != set(model.observation_keys):
        raise ValueError("Supply every natural observation key")
    query = select(model).filter_by(**key)
    if writer is not None:
        query = query.join(RawPayload, RawPayload.id == model.raw_payload_id).where(writer.captures)
    if captured_before is not None:
        if captured_before.utcoffset() is None:
            raise ValueError("captured_before must be timezone-aware")
        query = query.where(model.captured_at < captured_before)
    if before is not None:
        query = query.where(
            tuple_(model.observed_for, model.captured_at, model.raw_payload_id) < before
        )
    if raw_payload_id is not None:
        query = query.where(model.raw_payload_id == raw_payload_id).order_by(model.id.desc())
    else:
        query = query.order_by(
            model.observed_for.desc(),
            model.captured_at.desc(),
            model.raw_payload_id.desc(),
            model.id.desc(),
        )
    return session.scalar(query.limit(1))


def current_fields[T: ObservationRow](
    session: Session,
    model: type[T],
    *,
    key: dict[str, Any],
    writers: Sequence[Writer],
    captured_before: datetime | None = None,
) -> dict[str, T]:
    """Each owned field's provenance row from its writer (DEC-120); absent means missing.

    An owned null supersedes that writer's older values; nothing carries across writers.
    """
    owned = [name for writer in writers for name in writer.fields]
    if len(set(owned)) != len(owned) or not set(owned) <= set(model.__table__.columns.keys()):
        raise ValueError("Writers must own distinct model fields")
    current: dict[str, T] = {}
    for writer in writers:
        row = effective_observation(
            session, model, key=key, writer=writer, captured_before=captured_before
        )
        if row is not None:
            current |= dict.fromkeys(writer.fields, row)
    return current


def append_observation(
    session: Session, row: ObservationRow, *, writer: Writer | None = None
) -> bool:
    """Insert once per capture/parser; change-only for hashed listing/variant snapshots.

    The caller sets provenance and owns the transaction. A different parser always
    appends for an existing capture, even if its corrected values happen to match.
    A writer limits change-only to rows from that writer's captures (DEC-120).
    """
    if (
        not row.captured_at
        or row.captured_at.utcoffset() is None
        or not row.observed_for
        or not row.raw_payload_id
    ):
        raise ValueError("Observation requires aware captured_at, observed_for and raw_payload_id")
    if not row.parser_version or len(row.parser_version) > 80:
        raise ValueError("parser_version must contain 1 to 80 characters")
    model = type(row)
    key = {name: getattr(row, name) for name in model.observation_keys}
    previous = effective_observation(session, model, key=key, raw_payload_id=row.raw_payload_id)
    if isinstance(row, (ListingSnapshot, VariantSnapshot)) and previous is None:
        latest = effective_observation(
            session,
            model,
            key=key,
            before=(row.observed_for, row.captured_at, row.raw_payload_id),
            writer=writer,
        )
        if (
            isinstance(latest, (ListingSnapshot, VariantSnapshot))
            and latest.values_hash == row.values_hash
        ):
            return False
    values = {
        column.key: getattr(row, column.key)
        for column in model.__table__.columns
        if column.key != "id" and getattr(row, column.key) is not None
    }
    statement = (
        insert(model)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[*model.observation_keys, "raw_payload_id", "parser_version"]
        )
        .returning(model.id)
    )
    return session.scalar(statement) is not None
