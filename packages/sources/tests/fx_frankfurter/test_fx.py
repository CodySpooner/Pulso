import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import Integer, MetaData, create_engine, func, select
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import FxRate, RawPayload, SourceEvent
from pulso_core.money import convert_minor
from pulso_sources import fx_frankfurter
from pulso_sources.framework import Request, UpsertStats
from pulso_sources.fx_frankfurter import (
    SOURCE,
    FrankfurterAdapter,
    FxBackfillRange,
    Rate,
    backfill,
    plan,
    rate_as_of,
)
from pulso_sources.imports import ADAPTERS, ImportData, parse_csv

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def session() -> Iterator[Session]:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    metadata.tables["fx_rates"].create(engine)
    events = metadata.tables["source_events"]
    events.c.id.type = Integer()
    events.create(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "name,count,day", [("latest.json", 3, 19), ("history.json", 3, 19), ("outage.json", 6, 9)]
)
def test_parse_fixture(name: str, count: int, day: int) -> None:
    rows = FrankfurterAdapter().parse((FIXTURES / name).read_bytes())
    assert len(rows) == count
    assert rows[0].date == date(2026, 10, day) and rows[0].rate == Decimal(150)


def test_hand_checked_fixture_conversion() -> None:
    rate = FrankfurterAdapter().parse((FIXTURES / "latest.json").read_bytes())[0].rate
    assert convert_minor(123, "USD", "JPY", rate, rounding=ROUND_HALF_UP) == 185
    assert convert_minor(1500, "JPY", "USD", rate, rounding=ROUND_HALF_UP, inverse=True) == 1000
    with pytest.raises(FxBackfillRange):
        backfill(date(2026, 10, 22), date(2026, 10, 21))


@pytest.mark.parametrize(
    "body",
    [
        b'{"status":422}',
        b'[{"date":"bad","base":"USD","quote":"JPY","rate":1}]',
        b'[{"date":"2026-10-19","base":"USD","quote":"XYZ","rate":1}]',
        b'[{"date":"2026-10-19","base":"USD","quote":"JPY","rate":0}]',
        b'[{"date":"2026-10-19","base":"USD","quote":"JPY","rate":NaN}]',
    ],
)
def test_invalid_payload(body: bytes) -> None:
    with pytest.raises(ValueError):
        FrankfurterAdapter().parse(body)


def test_http_contract_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = Mock()
    response = connection.getresponse.return_value
    response.read.return_value = b"blocked"
    response.status = 429
    response.getheader.return_value = None
    response.getheaders.return_value = [("Retry-After", "3600")]
    transport = Mock(return_value=connection)
    monkeypatch.setattr(fx_frankfurter, "HTTPSConnection", transport)
    monkeypatch.setattr(
        fx_frankfurter, "get_settings", lambda: Mock(collector_request_timeout_seconds=30)
    )
    adapter = FrankfurterAdapter()
    result = adapter.fetch(Request(params={"base": "USD"}), user_agent="fixture-agent")
    assert result.status_code == 429 and result.headers["Retry-After"] == "3600"
    assert connection.request.call_args.args == ("GET", "/v2/rates?base=USD")
    assert connection.request.call_args.kwargs["headers"]["User-Agent"] == "fixture-agent"
    connection.close.assert_called_once()
    connection.request.side_effect = TimeoutError()
    with pytest.raises(ConnectionError):
        adapter.fetch(Request(), user_agent="fixture-agent")
    with pytest.raises(ValueError):
        adapter.fetch(Request(params={"providers": "ecb"}), user_agent="fixture-agent")


def test_cutoff_carry_forward_and_late_backfill(session: Session) -> None:
    for day, captured, rate in [(19, 19, "150"), (20, 22, "151"), (21, 22, "152")]:
        session.add(
            FxRate(
                date=date(2026, 10, day),
                base="USD",
                quote="JPY",
                source=SOURCE,
                rate=Decimal(rate),
                observed_for=date(2026, 10, day),
                captured_at=datetime(2026, 10, captured, tzinfo=UTC),
                raw_payload_id=day,
            )
        )
    session.flush()
    assert rate_as_of(session, "JPY", date(2026, 10, 18)) is None
    for day, expected in [(19, "150"), (20, "150"), (21, "150"), (22, "152"), (25, "152")]:
        row = rate_as_of(session, "JPY", date(2026, 10, day))
        assert row is not None and row.rate == Decimal(expected)


def test_plan_refills_outage_from_slowest_pair(session: Session) -> None:
    assert list(plan(session, date(2026, 10, 22))[0].requests)[0].params["from"] == "2025-01-01"
    for quote in fx_frankfurter.QUOTES:
        day = 19 if quote == "JPY" else 20
        session.add(
            FxRate(
                date=date(2026, 10, day),
                base="USD",
                quote=quote,
                source=SOURCE,
                rate=Decimal(1),
                observed_for=date(2026, 10, day),
                captured_at=datetime(2026, 10, day, tzinfo=UTC),
                raw_payload_id=day,
            )
        )
    targets = plan(session, date(2026, 10, 22))
    requests = list(targets[0].requests)
    assert len(requests) == 2
    assert requests[0].params["from"] == "2026-10-20"
    assert requests[0].params["to"] == "2026-10-21"
    assert "from" not in requests[1].params


def test_one_quote_without_rates_does_not_pin_the_watermark(session: Session) -> None:
    # P1-32 L7 (probe F2): a quote that never returns no longer restarts from 2025-01-01.
    for quote in fx_frankfurter.QUOTES[1:]:
        session.add(
            FxRate(
                date=date(2026, 10, 21),
                base="USD",
                quote=quote,
                source=SOURCE,
                rate=Decimal(1),
                observed_for=date(2026, 10, 21),
                captured_at=datetime(2026, 10, 21, tzinfo=UTC),
                raw_payload_id=1,
            )
        )
    backfill_request = list(plan(session, date(2026, 10, 22))[0].requests)[0]
    assert backfill_request.params["from"] == "2026-09-21"
    assert backfill_request.params["to"] == "2026-10-21"


def test_refill_replay_and_conflict_keep_first_rate(session: Session) -> None:
    adapter = FrankfurterAdapter()
    first = RawPayload(id=1, source_id=4, captured_at=datetime(2026, 10, 19, tzinfo=UTC))
    late = RawPayload(id=2, source_id=4, captured_at=datetime(2026, 10, 22, tzinfo=UTC))
    adapter.upsert(
        session, adapter.parse((FIXTURES / "latest.json").read_bytes()), first, parser_version="1"
    )
    history = adapter.parse((FIXTURES / "history.json").read_bytes())
    assert adapter.upsert(session, history, late, parser_version="1").inserted == 2
    assert adapter.upsert(session, history, late, parser_version="1").inserted == 0
    row = session.get_one(FxRate, (date(2026, 10, 20), "USD", "JPY", SOURCE))
    assert row.raw_payload_id == late.id and row.observed_for == date(2026, 10, 20)
    assert row.captured_at.replace(tzinfo=UTC) == late.captured_at
    corrected = [history[1].model_copy(update={"rate": Decimal(999)})]
    for _ in range(2):
        assert adapter.upsert(session, corrected, late, parser_version="2").inserted == 0
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1
    assert session.get_one(FxRate, (date(2026, 10, 20), "USD", "JPY", SOURCE)).rate == Decimal(151)
    # DEC-230: rows dated after the capture's UTC date are skipped, not rejected.
    assert adapter.upsert(session, history, first, parser_version="1") == UpsertStats(unchanged=1)


@pytest.mark.parametrize(
    ("captured_at", "kept", "skipped"),
    [
        (datetime(2026, 10, 20, tzinfo=UTC), [19, 20], "2026-10-21"),
        (datetime(2026, 10, 19, 23, 59, 59, tzinfo=UTC), [19], "2026-10-20,2026-10-21"),
        # 20:00 at UTC-5 is 01:00Z on the 20th: the UTC date decides, not the local one.
        (datetime(2026, 10, 19, 20, tzinfo=timezone(timedelta(hours=-5))), [19, 20], "2026-10-21"),
    ],
    ids=["00:00Z", "23:59:59Z", "aware-non-utc"],
)
def test_next_day_rows_skipped_with_named_evidence(
    session: Session,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    captured_at: datetime,
    kept: list[int],
    skipped: str,
) -> None:
    # XR-10: the DEC-230 skip is logged by name, not only implied by the row counts.
    rows = [Rate(date=date(2026, 10, d), base="USD", quote="JPY", rate=d) for d in (19, 20, 21)]
    payload = RawPayload(id=7, source_id=4, captured_at=captured_at)
    monkeypatch.setattr(logging.getLogger("pulso"), "propagate", True)
    with caplog.at_level(logging.INFO, "pulso"):
        assert FrankfurterAdapter().upsert(session, rows, payload, parser_version="1").inserted
    assert sorted(row.date.day for row in session.scalars(select(FxRate))) == kept
    line = f"fx_next_day_rows_skipped count={3 - len(kept)} dates={skipped} raw_payload_id=7"
    assert caplog.messages == [line]


def test_csv_registration_validation_and_manual_provenance(session: Session) -> None:
    body = b"date,base,quote,rate\n2026-10-19,USD,JPY,150\n2026-10-20,USD,JPY,0\n"
    parsed = parse_csv("fx_frankfurter", body, as_of=date(2026, 10, 22))
    assert len(parsed.rows) == len(parsed.errors) == 1
    adapter = ADAPTERS["fx_frankfurter"](ImportData("csv", parsed, None))
    payload = RawPayload(id=1, source_id=4, captured_at=datetime(2026, 10, 22, tzinfo=UTC))
    assert adapter.upsert(session, adapter.parse(body), payload, parser_version="1").inserted == 1
    assert session.get_one(FxRate, (date(2026, 10, 19), "USD", "JPY", "manual")).rate == 150
    for rate in ["NaN", "Infinity", "1e10", "0.000000001"]:
        invalid = body.splitlines()[0] + f"\n2026-10-19,USD,JPY,{rate}\n".encode()
        assert parse_csv("fx_frankfurter", invalid).errors


def test_five_day_outage_backfill_preserves_historical_features(session: Session) -> None:
    adapter = FrankfurterAdapter()
    rows = adapter.parse((FIXTURES / "outage.json").read_bytes())
    before = RawPayload(id=1, source_id=4, captured_at=datetime(2026, 10, 9, tzinfo=UTC))
    after = RawPayload(id=2, source_id=4, captured_at=datetime(2026, 10, 17, tzinfo=UTC))
    adapter.upsert(session, rows[:1], before, parser_version="1")
    assert adapter.upsert(session, rows, after, parser_version="1").inserted == 5
    assert adapter.upsert(session, rows, after, parser_version="1").inserted == 0
    assert session.scalar(select(func.count()).select_from(FxRate)) == 6
    for day, value in [(16, 150), (17, 155)]:
        rate = rate_as_of(session, "JPY", date(2026, 10, day))
        assert rate is not None and rate.rate == value
