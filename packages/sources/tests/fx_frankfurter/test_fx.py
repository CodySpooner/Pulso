from collections.abc import Iterator
from datetime import UTC, date, datetime
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
from pulso_sources.framework import Request
from pulso_sources.fx_frankfurter import SOURCE, FrankfurterAdapter, backfill, plan, rate_as_of
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


@pytest.mark.parametrize("name,count", [("latest.json", 3), ("history.json", 3)])
def test_parse_fixture(name: str, count: int) -> None:
    rows = FrankfurterAdapter().parse((FIXTURES / name).read_bytes())
    assert len(rows) == count
    assert rows[0].date == date(2026, 10, 19) and rows[0].rate == Decimal(150)


def test_hand_checked_fixture_conversion() -> None:
    rate = FrankfurterAdapter().parse((FIXTURES / "latest.json").read_bytes())[0].rate
    assert convert_minor(123, "USD", "JPY", rate, rounding=ROUND_HALF_UP) == 185
    assert convert_minor(1500, "JPY", "USD", 1 / rate, rounding=ROUND_HALF_UP) == 1000
    with pytest.raises(ValueError):
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
    with pytest.raises(ValueError, match="capture date"):
        adapter.upsert(session, history, first, parser_version="1")


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
