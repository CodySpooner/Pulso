from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectionGap,
    CollectorRun,
    CollectorRunTarget,
    FxRate,
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    SearchTrend,
    ShippingOption,
    SourceEvent,
    VariantSnapshot,
)

pytestmark = pytest.mark.db
DAY = date(2026, 10, 22)
AT = datetime(2026, 10, 22, 12, tzinfo=UTC)


@pytest.fixture
def evidence(db_engine: Engine) -> Iterator[tuple[Session, CollectorRun, RawPayload, Listing]]:
    with Session(db_engine) as session, session.begin():
        run = CollectorRun(source_id=1, trigger="csv", queued_at=AT)
        listing = Listing(source_id=1, external_id="fixture", url="https://example.test", title="X")
        session.add_all([run, listing])
        session.flush()
        payload = RawPayload(
            source_id=1,
            run_id=run.id,
            request={},
            bytes=0,
            sha256="0" * 64,
            status_code=304,
            captured_at=AT,
        )
        session.add(payload)
        session.flush()
        yield session, run, payload, listing


@pytest.mark.parametrize("table", [ListingSnapshot, VariantSnapshot, ShippingOption, SearchTrend])
def test_parser_replay_rejected_and_correction_appends(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
    table: type[ListingSnapshot | VariantSnapshot | ShippingOption | SearchTrend],
) -> None:
    session, _, payload, listing = evidence
    values: dict[str, object] = {
        "raw_payload_id": payload.id,
        "observed_for": DAY,
        "captured_at": AT,
        "parser_version": "1",
    }
    if table is SearchTrend:
        values.update(
            source_id=1,
            keyword="lamp",
            geo="US",
            window="today 3-m",
            granularity="day",
            metric="relative_interest",
            value=40,
        )
    elif table is ShippingOption:
        values.update(
            listing_id=listing.id,
            destination_country="US",
            method="standard",
            cost_minor=123,
            currency="USD",
        )
    else:
        values.update(values_hash="a" * 64, currency="USD")
        if table is VariantSnapshot:
            variant = ListingVariant(listing_id=listing.id, external_id="v1")
            session.add(variant)
            session.flush()
            values["variant_id"] = variant.id
        else:
            values["listing_id"] = listing.id
    original = session.scalar(insert(table).values(**values).returning(table.id))
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(insert(table).values(**values))
    correction = session.scalar(
        insert(table).values(**(values | {"parser_version": "2"})).returning(table.id)
    )
    assert correction != original
    assert session.scalars(select(table.parser_version).order_by(table.id)).all() == ["1", "2"]


def test_freight_dimensions_and_nullable_identity(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, _, payload, listing = evidence
    statement = insert(ShippingOption).values(
        listing_id=listing.id,
        raw_payload_id=payload.id,
        observed_for=DAY,
        destination_country="US",
        method="standard",
        cost_minor=100,
        currency="USD",
    )
    for origin, quantity in [(None, 1), (None, 2), ("CN", 1), ("US", 1)]:
        quote = statement.values(origin_country=origin, quantity=quantity)
        session.execute(quote)
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(quote)
    assert len(session.scalars(select(ShippingOption)).all()) == 4


def test_import_identity_does_not_deduplicate_live_captures(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, run, payload, _ = evidence
    statement = insert(RawPayload).values(
        source_id=1,
        run_id=run.id,
        request={},
        bytes=0,
        sha256=payload.sha256,
    )
    for version in [None, None, "csv-v1", "csv-v2"]:
        session.execute(statement.values(template_version=version))
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(statement.values(template_version="csv-v1"))
    session.execute(statement.values(source_id=2, template_version="csv-v1"))
    assert len(session.scalars(select(RawPayload)).all()) == 6


def test_fx_retains_first_rate_per_agreed_exception(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, _, payload, _ = evidence
    statement = insert(FxRate).values(
        date=DAY,
        base="USD",
        quote="EUR",
        source="fx_frankfurter",
        rate="0.9",
        observed_for=DAY,
        raw_payload_id=payload.id,
    )
    session.execute(statement)
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(statement.values(parser_version="2", rate="0.8"))


def test_queue_and_job_qualified_success_slots(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, run, _, _ = evidence
    assert run.status == "queued" and run.started_at is None and run.queued_at == AT
    for job in ("catalog", "inventory"):
        statement = insert(CollectorRun).values(
            source_id=1,
            trigger="schedule",
            status="success",
            started_at=AT,
            slot_key=f"{job}:2026-10-22",
        )
        session.execute(statement)
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(statement.values(trigger="catchup"))
        session.execute(statement.values(status="failed"))
        session.execute(statement.values(trigger="manual"))


def test_source_events_reject_update_delete_and_truncate(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, _, _, _ = evidence
    session.add(SourceEvent(source_id=1, action="auto_disable", reason="fixture block"))
    session.flush()
    for sql in (
        "UPDATE source_events SET action = 'enable'",
        "DELETE FROM source_events",
        "TRUNCATE source_events",
    ):
        with pytest.raises(DBAPIError, match="append-only"), session.begin_nested():
            session.execute(text(sql))
    assert session.scalar(select(SourceEvent.action)) == "auto_disable"


def test_coverage_counts_targets_including_304_without_multiplying_runs(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, run, payload, _ = evidence
    run.status, run.rows_inserted = "partial", 7
    for scope, target, status in [
        ("catalog", "store-a", "success"),
        ("inventory", "store-a", "failed"),
        ("catalog", "store-b", "failed"),
    ]:
        session.add(
            CollectorRunTarget(
                run_id=run.id,
                scope=scope,
                target_id=target,
                status=status,
                raw_payload_id=payload.id if status == "success" else None,
                captured_at=AT,
            )
        )
    session.flush()
    row = session.execute(text("SELECT * FROM source_daily_coverage WHERE source_id = 1")).one()
    assert (row.day, row.status, row.runs, row.rows, row.targets, row.successful_targets) == (
        DAY,
        "partial",
        1,
        7,
        3,
        1,
    )
    assert session.scalar(select(ListingSnapshot.id)) is None
    with pytest.raises(IntegrityError), session.begin_nested():
        session.execute(
            insert(CollectorRunTarget).values(
                run_id=run.id, scope="catalog", target_id="no-evidence", status="success"
            )
        )


def test_coverage_utc_days_gaps_and_no_source_wide_success(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
) -> None:
    session, run, payload, _ = evidence
    run.status = "success"
    run.queued_at = datetime(2026, 10, 23, 1, tzinfo=UTC)
    session.add(
        CollectionGap(
            source_id=1,
            slot_key="catalog:2026-10-20",
            slot_start=datetime(2026, 10, 20, tzinfo=UTC),
            slot_end=datetime(2026, 10, 22, tzinfo=UTC),
            reason="host_offline",
        )
    )
    session.flush()
    session.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
    rows = session.execute(
        text("SELECT day, status, runs FROM source_daily_coverage ORDER BY day")
    ).all()
    assert [tuple(row) for row in rows] == [
        (date(2026, 10, 20), "gap", 0),
        (date(2026, 10, 21), "gap", 0),
        (date(2026, 10, 23), "unknown", 1),
    ]
    session.add(
        CollectorRunTarget(
            run_id=run.id,
            scope="catalog",
            target_id="store-a",
            status="success",
            raw_payload_id=payload.id,
            captured_at=datetime(2026, 10, 23, 1, tzinfo=UTC),
        )
    )
    session.flush()
    row = session.execute(
        text("SELECT * FROM source_daily_coverage ORDER BY day DESC LIMIT 1")
    ).one()
    assert (row.day, row.status, row.runs, row.rows) == (date(2026, 10, 23), "success", 1, 0)
    session.execute(text("UPDATE collection_gaps SET filled_by_run_id = :run"), {"run": run.id})
    rows = session.execute(
        text("SELECT day, status, runs FROM source_daily_coverage ORDER BY day")
    ).all()
    assert [tuple(row) for row in rows] == [
        (date(2026, 10, 20), "filled", 0),
        (date(2026, 10, 21), "filled", 0),
        (date(2026, 10, 23), "success", 1),
    ]


@pytest.mark.parametrize(
    "run_status,target_statuses,gap,expected",
    [
        ("success", ("success",), None, "success"),
        ("partial", ("success", "failed"), None, "partial"),
        ("failed", (), "unfilled", "gap"),
        ("running", (), None, "running"),
        ("queued", (), None, "queued"),
        ("failed", (), None, "failed"),
        ("blocked", (), None, "failed"),
        ("partial", (), None, "failed"),
        ("success", ("failed",), None, "failed"),
        ("success", (), "filled", "filled"),
        ("success", (), None, "unknown"),
        ("partial", ("success", "failed"), "unfilled", "partial"),
        ("success", ("success",), "unfilled", "partial"),
        ("running", (), "unfilled", "gap"),
    ],
)
def test_coverage_status_branches(
    evidence: tuple[Session, CollectorRun, RawPayload, Listing],
    run_status: str,
    target_statuses: tuple[str, ...],
    gap: str | None,
    expected: str,
) -> None:
    session, run, payload, _ = evidence
    run.status = run_status
    for target, status in enumerate(target_statuses):
        session.add(
            CollectorRunTarget(
                run_id=run.id,
                scope="catalog",
                target_id=str(target),
                status=status,
                raw_payload_id=payload.id if status == "success" else None,
                captured_at=AT,
            )
        )
    if gap:
        session.add(
            CollectionGap(
                source_id=1,
                slot_key="catalog:2026-10-22",
                slot_start=datetime(2026, 10, 22, tzinfo=UTC),
                slot_end=datetime(2026, 10, 23, tzinfo=UTC),
                reason="host_offline",
                filled_by_run_id=run.id if gap == "filled" else None,
            )
        )
    session.flush()
    assert session.execute(text("SELECT day, status FROM source_daily_coverage")).one() == (
        DAY,
        expected,
    )
