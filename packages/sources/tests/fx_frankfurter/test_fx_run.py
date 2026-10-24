"""data-06: the first live run ended partial/ValueError; each FX check now names itself.

Synthetic bodies through the real run lifecycle; a fake fetch, never a connection.
"""

import io
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import CollectorRun, FxRate, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources import framework, fx_frankfurter, storage
from pulso_sources.framework import Request, Response, Target, enqueue_run, execute_run, lifecycle
from pulso_sources.fx_frankfurter import FrankfurterAdapter, plan

# The first live run: 2026-10-24 18:50Z, already 2026-10-25 east of UTC+5:10.
NOW = datetime(2026, 10, 24, 18, 50, tzinfo=UTC)


def body(*rows: tuple[int, str, float]) -> bytes:
    return json.dumps(
        [{"date": f"2026-10-{d}", "base": "USD", "quote": q, "rate": r} for d, q, r in rows]
    ).encode()


BACKFILL = body((23, "EUR", 0.9), (23, "JPY", 150))


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://fixture@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "fixture")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "fixture")
    settings = Settings()
    settings.collectors_live = True
    settings.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    return settings


@pytest.fixture
def session(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in [
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
        "fx_rates",
    ]:
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSON):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)
    objects: dict[str, bytes] = {}
    client = MagicMock()
    client.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(lifecycle, "datetime", Mock(now=lambda _: NOW))
    # A real connection attempt would surface as error_code AssertionError.
    monkeypatch.setattr(fx_frankfurter, "HTTPSConnection", Mock(side_effect=AssertionError))
    try:
        with Session(engine) as session:
            session.add(
                Source(id=4, key="fx_frankfurter", name="FX", type="api", phase=1, enabled=True)
            )
            session.commit()
            yield session
    finally:
        engine.dispose()


def collect(
    session: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    latest: bytes | None,
    targets: list[Target] | None = None,
) -> CollectorRun:
    """The first catch-up run: plan's backfill gets BACKFILL, latest gets `latest`."""
    if latest is not None:

        def fetch(_: Any, request: Request, *, user_agent: str) -> Response:
            return Response(BACKFILL if "from" in request.params else latest, 200)

        monkeypatch.setattr(FrankfurterAdapter, "fetch", fetch)
    run = enqueue_run(
        session, source_id=4, trigger="catchup", slot_key="fx:2026-10-24", publish=lambda _: None
    )
    targets = plan(session, NOW.date()) if targets is None else targets
    return execute_run(session, run.id, FrankfurterAdapter(), targets, settings=settings)


def stored(session: Session) -> set[tuple[date, str]]:
    return set(session.execute(select(FxRate.date, FxRate.quote)).tuples())


def test_next_day_row_is_skipped_and_the_rest_of_the_capture_stored(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    latest = body((24, "JPY", 151), (25, "EUR", 0.91), (24, "KWD", 0.3075))
    run = collect(session, settings, monkeypatch, latest)
    assert (run.status, run.error_code) == ("success", None)
    assert stored(session) == {
        (date(2026, 10, 23), "EUR"),
        (date(2026, 10, 23), "JPY"),
        (date(2026, 10, 24), "JPY"),
        (date(2026, 10, 24), "KWD"),
    }
    # DEC-230: the skipped row is counted (fetched - inserted - unchanged), never stored.
    assert (run.rows_fetched, run.rows_inserted, run.rows_unchanged) == (5, 4, 0)
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 2


@pytest.mark.parametrize(
    "latest,code",
    [
        (b'{"rates":{"JPY":151}}', "FxNotRateArray"),
        (body((24, "JPY", 151), (24, "JPY", 152)), "FxDuplicateRow"),
        # Recorded under their own names, so neither was the first run's ValueError.
        (
            b'{"date":"2026-10-24","base":"USD","quote":"JPY","rate":151}\n{"x":1}\n',
            "JSONDecodeError",
        ),
        (body((24, "XYZ", 1)), "ValidationError"),
    ],
)
def test_latest_check_names_itself_and_keeps_the_backfill(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch, latest: bytes, code: str
) -> None:
    run = collect(session, settings, monkeypatch, latest)
    assert (run.status, run.error_code, run.error_message) == ("partial", code, code)
    assert stored(session) == {(date(2026, 10, 23), "EUR"), (date(2026, 10, 23), "JPY")}


def test_capture_metadata_check_names_itself(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(FrankfurterAdapter, "parser_version", "")
    run = collect(session, settings, monkeypatch, body((24, "JPY", 151)))
    assert (run.status, run.error_code) == ("partial", "FxCaptureMetadata")
    assert stored(session) == set()


def test_unsupported_request_names_itself_before_any_connection(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    targets = [Target("fx", "daily", [Request(params={"providers": "ecb"})])]
    run = collect(session, settings, monkeypatch, None, targets)
    assert (run.status, run.error_code) == ("failed", "FxUnsupportedRequest")
