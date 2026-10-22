from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import Integer, MetaData, create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    RawPayload,
    ShippingOption,
    VariantSnapshot,
)
from pulso_sources.framework import append_observation, effective_observation

AT = datetime(2026, 10, 22, tzinfo=UTC)


def observation(
    capture_id: int = 1, parser: str = "9", value: str = "a", *, at: datetime = AT
) -> ListingSnapshot:
    return ListingSnapshot(
        listing_id=1,
        raw_payload_id=capture_id,
        parser_version=parser,
        captured_at=at,
        observed_for=at.date(),
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


@pytest.fixture
def offline_session() -> Iterator[Session]:
    # SQLite exercises the SQL path; the separate PG test owns FK/NULLS NOT DISTINCT checks.
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    try:
        for name in ("listing_snapshots", "variant_snapshots", "shipping_options"):
            table = metadata.tables[name]
            table.c.id.type = Integer()
            table.create(engine)
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_one_capture_keeps_distinct_variants_and_warehouses_once(offline_session: Session) -> None:
    session = offline_session
    listing = observation()
    assert append_observation(session, listing)
    assert not append_observation(session, listing)
    for variant in (1, 2):
        row = VariantSnapshot(
            variant_id=variant,
            raw_payload_id=1,
            parser_version="1",
            captured_at=AT,
            observed_for=AT.date(),
            currency="USD",
            values_hash=str(variant) * 64,
            price_minor=100 * variant,
        )
        assert append_observation(session, row)
        assert not append_observation(session, row)
    for origin in ("US", "CN"):
        quote = ShippingOption(
            listing_id=1,
            variant_id=1,
            origin_country=origin,
            destination_country="US",
            quantity=1,
            method="standard",
            raw_payload_id=1,
            parser_version="1",
            captured_at=AT,
            observed_for=AT.date(),
            cost_minor=100,
            currency="USD",
        )
        assert append_observation(session, quote)
        assert not append_observation(session, quote)
    for model, expected in ((ListingSnapshot, 1), (VariantSnapshot, 2), (ShippingOption, 2)):
        assert session.scalar(select(func.count()).select_from(model)) == expected


def test_replay_and_parser_order_execute_offline(offline_session: Session) -> None:
    session = offline_session
    assert append_observation(session, observation(parser="9", value="a"))
    assert not append_observation(session, observation(parser="9", value="a"))
    assert append_observation(session, observation(parser="10", value="b"))
    assert not append_observation(session, observation(parser="10", value="b"))
    effective = effective_observation(
        session, ListingSnapshot, key={"listing_id": 1}, raw_payload_id=1
    )
    assert effective is not None and effective.parser_version == "10"
    assert not append_observation(session, observation(capture_id=2, parser="10", value="b"))
    assert append_observation(session, observation(capture_id=3, parser="10", value="c"))
    assert not append_observation(session, observation(parser="9", value="a"))
    rows = list(session.scalars(select(ListingSnapshot).order_by(ListingSnapshot.id)))
    assert [row.values_hash for row in rows] == ["a" * 64, "b" * 64, "c" * 64]


@pytest.mark.parametrize("step", [timedelta(days=1), timedelta(0)])
def test_skipped_capture_correction_compares_only_prior_captures(
    offline_session: Session, step: timedelta
) -> None:
    session = offline_session
    assert append_observation(session, observation(1, at=AT - 2 * step))
    assert not append_observation(session, observation(2, at=AT - step))
    assert append_observation(session, observation(3, value="b"))
    assert append_observation(session, observation(2, parser="10", value="b", at=AT - step))
    assert not append_observation(session, observation(2, parser="10", value="b", at=AT - step))
    corrected = effective_observation(
        session, ListingSnapshot, key={"listing_id": 1}, before=(AT, 3)
    )
    assert corrected is not None and corrected.raw_payload_id == 2
    assert corrected.parser_version == "10" and corrected.values_hash == "b" * 64


def test_out_of_order_first_capture_is_not_suppressed(offline_session: Session) -> None:
    assert append_observation(offline_session, observation(2))
    assert append_observation(offline_session, observation(1, at=AT - timedelta(days=1)))
    assert (
        effective_observation(
            offline_session,
            ListingSnapshot,
            key={"listing_id": 1},
            before=(AT - timedelta(days=1), 1),
        )
        is None
    )


def test_historical_import_does_not_replace_current_or_live_baseline(
    offline_session: Session,
) -> None:
    session = offline_session
    assert append_observation(session, observation(1))
    historical = observation(2, value="b", at=AT + timedelta(hours=1))
    historical.observed_for = date(2026, 9, 1)
    assert append_observation(session, historical)
    current = effective_observation(session, ListingSnapshot, key={"listing_id": 1})
    assert current is not None and current.raw_payload_id == 1
    assert not append_observation(session, observation(3, at=AT + timedelta(days=1)))


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
