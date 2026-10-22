from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import Integer, MetaData, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import CollectorRun, Listing, ListingSnapshot, RawPayload, ShippingOption
from pulso_sources.framework import append_observation, effective_observation

AT = datetime(2026, 10, 22, tzinfo=UTC)


def observation(capture_id: int = 1, parser: str = "9", value: str = "a") -> ListingSnapshot:
    return ListingSnapshot(
        listing_id=1,
        raw_payload_id=capture_id,
        parser_version=parser,
        captured_at=AT,
        observed_for=AT.date(),
        currency="USD",
        values_hash=value * 64,
        price_min_minor=100,
    )


def test_effective_query_orders_numeric_id_not_parser_label() -> None:
    session = Mock(spec=Session)
    session.scalar.return_value = observation(parser="10")
    assert (
        effective_observation(session, ListingSnapshot, key={"listing_id": 1}, raw_payload_id=1)
        is session.scalar.return_value
    )
    query = str(session.scalar.call_args.args[0].compile())
    assert "ORDER BY listing_snapshots.id DESC" in query
    assert "ORDER BY listing_snapshots.parser_version" not in query
    with pytest.raises(ValueError, match="every natural"):
        effective_observation(session, ListingSnapshot, key={})


def test_append_uses_null_safe_natural_key_and_conflict_do_nothing() -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, 1]
    row = ShippingOption(
        listing_id=1,
        variant_id=None,
        origin_country=None,
        destination_country="US",
        quantity=2,
        method="standard",
        raw_payload_id=1,
        parser_version="1",
        captured_at=AT,
        observed_for=AT.date(),
        cost_minor=100,
        currency="USD",
    )
    assert append_observation(session, row)
    read = str(session.scalar.call_args_list[0].args[0].compile())
    write = str(session.scalar.call_args_list[-1].args[0].compile())
    assert "variant_id IS NULL" in read and "origin_country IS NULL" in read
    assert "quantity" in write and "parser_version) DO NOTHING" in write
    assert "UPDATE" not in write


def test_change_only_compares_effective_row_but_correction_always_appends() -> None:
    session = Mock(spec=Session)
    session.scalar.side_effect = [None, observation(parser="10")]
    assert not append_observation(session, observation(capture_id=2))
    assert session.scalar.call_count == 2
    session.scalar.reset_mock(side_effect=True)
    session.scalar.side_effect = [observation(parser="9"), 2]
    assert append_observation(session, observation(parser="10"))


def test_replay_and_parser_order_execute_offline() -> None:
    # SQLite exercises the SQL path; the separate PG test owns FK/NULLS NOT DISTINCT checks.
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    snapshots = metadata.tables["listing_snapshots"]
    snapshots.c.id.type = Integer()
    engine = create_engine("sqlite://")
    try:
        snapshots.create(engine)
        with Session(engine) as session:
            assert append_observation(session, observation(parser="9", value="a"))
            assert not append_observation(session, observation(parser="9", value="a"))
            assert append_observation(session, observation(parser="10", value="b"))
            assert not append_observation(session, observation(parser="10", value="b"))
            effective = effective_observation(
                session, ListingSnapshot, key={"listing_id": 1}, raw_payload_id=1
            )
            assert effective is not None and effective.parser_version == "10"
            assert not append_observation(
                session, observation(capture_id=2, parser="10", value="b")
            )
            assert append_observation(session, observation(capture_id=3, parser="10", value="c"))
            assert not append_observation(session, observation(parser="9", value="a"))
            rows = list(session.scalars(select(ListingSnapshot).order_by(ListingSnapshot.id)))
            assert [row.values_hash for row in rows] == ["a" * 64, "b" * 64, "c" * 64]
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "field,value",
    [
        ("captured_at", AT.replace(tzinfo=None)),
        ("captured_at", None),
        ("raw_payload_id", None),
        ("observed_for", None),
        ("parser_version", ""),
        ("parser_version", "x" * 81),
    ],
)
def test_provenance_required(field: str, value: object) -> None:
    row = observation()
    setattr(row, field, value)
    with pytest.raises(ValueError):
        append_observation(Mock(spec=Session), row)


@pytest.mark.db
def test_replay_correction_and_change_only_on_postgres(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        run = CollectorRun(source_id=1, trigger="fixture")
        listing = Listing(
            source_id=1, external_id="fixture", url="https://example.test", title="Fixture"
        )
        session.add_all([run, listing])
        session.flush()
        captures = [
            RawPayload(
                source_id=1, run_id=run.id, captured_at=AT, request={}, bytes=0, sha256="a" * 64
            )
            for _ in range(3)
        ]
        session.add_all(captures)
        session.flush()

        def append(capture: int, parser: str, value: str) -> bool:
            row = observation(captures[capture].id, parser, value)
            row.listing_id = listing.id
            return append_observation(session, row)

        assert append(0, "9", "a")
        assert not append(0, "9", "a")
        assert append(0, "10", "b")
        assert not append(0, "10", "b")
        effective = effective_observation(
            session, ListingSnapshot, key={"listing_id": listing.id}, raw_payload_id=captures[0].id
        )
        assert effective is not None and effective.parser_version == "10"
        assert not append(1, "10", "b")
        assert append(2, "10", "c")
        # Replaying an older parser cannot revert the effective corrected row.
        assert not append(0, "9", "a")
        rows = list(session.scalars(select(ListingSnapshot).order_by(ListingSnapshot.id)))
        assert [row.values_hash for row in rows] == ["a" * 64, "b" * 64, "c" * 64]
