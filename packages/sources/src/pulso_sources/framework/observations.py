"""Append observations; FX's first-rate rule remains adapter-owned (DEC-060)."""

from datetime import datetime
from typing import Any

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import ListingSnapshot, SearchTrend, ShippingOption, VariantSnapshot

type ObservationRow = ListingSnapshot | VariantSnapshot | ShippingOption | SearchTrend


def effective_observation[T: ObservationRow](
    session: Session,
    model: type[T],
    *,
    key: dict[str, Any],
    raw_payload_id: int | None = None,
    before: tuple[datetime, int] | None = None,
) -> T | None:
    """Latest observed day/capture, or greatest id in one capture; before is exclusive."""
    if set(key) != set(model.observation_keys):
        raise ValueError("Supply every natural observation key")
    query = select(model).filter_by(**key)
    if before is not None:
        query = query.where(tuple_(model.captured_at, model.raw_payload_id) < before)
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


def append_observation(session: Session, row: ObservationRow) -> bool:
    """Insert once per capture/parser; change-only for hashed listing/variant snapshots.

    The caller sets provenance and owns the transaction. A different parser always
    appends for an existing capture, even if its corrected values happen to match.
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
            session, model, key=key, before=(row.captured_at, row.raw_payload_id)
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
