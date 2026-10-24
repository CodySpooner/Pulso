"""In-container seeds/enable/disable/health logic on SQLite or a test DB; no collector DB."""

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from collector import sources
from pulso_core.models import CollectionGap, CollectorRun, HostHeartbeat, Source, SourceEvent

PRIVATE = "owner-fixture.test"
DEADLINE = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    metadata = MetaData()
    engine = create_engine("sqlite://")
    tables = ("sources", "source_events", "host_heartbeats", "collector_runs", "collection_gaps")
    for name in tables:
        table = Source.metadata.tables[name].to_metadata(metadata)
        for column in table.columns:
            if column.name == "id" and name != "sources":
                column.type = Integer()  # SQLite autoincrements only INTEGER keys
            if column.name in ("config", "params"):
                column.type, column.server_default = JSON(), None
        table.create(engine)
    with Session(engine) as session, session.begin():
        for i, key in enumerate(sources.SOURCES, 1):
            session.add(Source(id=i, key=key, name=key, type="api", phase=1, config={}))
        session.add(Source(id=9, key="backup", name="backup", type="ops", phase=1, config={}))
    yield engine
    engine.dispose()


def payload(stores: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    approval = {
        "version": "seed_v1",
        "status": "approved",
        "approved_on": (datetime.now(UTC).date() - timedelta(days=1)).isoformat(),
        "decision": "DEC-011",
    }
    entries = {
        "shopify_stores": stores or [{"domain": PRIVATE, "name": "Owner", "enabled": True}],
        "cj": [{"name": "Pet Supplies", "enabled": False}],
        "google_trends": [{"keyword": "cat tree", "geo": "US", "tz": 0, "enabled": True}],
    }
    return {key: {**approval, "entries": rows} for key, rows in entries.items()}


def call(engine: Engine, op: str, *args: Any) -> dict[str, Any]:
    with Session(engine) as session, session.begin():
        result: dict[str, Any] = getattr(sources, op)(session, *args)
        return result


def state(engine: Engine, key: str) -> tuple[Source, list[SourceEvent]]:
    with Session(engine, expire_on_commit=False) as session:
        source = session.scalars(select(Source).where(Source.key == key)).one()
        events = list(
            session.scalars(select(SourceEvent).where(SourceEvent.source_id == source.id))
        )
        return source, events


def test_enable_is_audited_idempotent_and_keeps_retry_deadline(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        fx = session.scalars(select(Source).where(Source.key == "fx_frankfurter")).one()
        fx.retry_not_before, fx.consecutive_block_count = DEADLINE, 2
    assert call(engine, "enable", "fx_frankfurter") == {"changed": True, "targets": None}
    assert call(engine, "enable", "fx_frankfurter") == {"changed": False, "targets": None}
    source, events = state(engine, "fx_frankfurter")
    assert source.enabled and source.status == "active"
    assert source.retry_not_before is not None
    assert source.retry_not_before.replace(tzinfo=UTC) == DEADLINE
    assert source.consecutive_block_count == 2
    assert [(e.actor, e.action) for e in events] == [("collector-cli", "enable")]


def test_blocked_source_is_never_reenabled(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        fx = session.scalars(select(Source).where(Source.key == "fx_frankfurter")).one()
        fx.status, fx.disabled_reason = "blocked", "consecutive_blocks:http_429"
    assert call(engine, "enable", "fx_frankfurter") == {"refused": "blocked"}
    source, events = state(engine, "fx_frankfurter")
    assert not source.enabled and source.status == "blocked" and events == []
    assert call(engine, "disable", "fx_frankfurter") == {"changed": False}
    assert state(engine, "fx_frankfurter")[0].status == "blocked"


@pytest.mark.parametrize("key", ["shopify_stores", "cj", "google_trends"])
def test_seed_sources_need_approved_targets(engine: Engine, key: str) -> None:
    assert call(engine, "enable", key) == {"refused": "no_approved_targets"}
    call(engine, "seeds", payload())
    expected = (
        {"refused": "no_approved_targets"} if key == "cj" else {"changed": True, "targets": 1}
    )
    assert call(engine, "enable", key) == expected
    assert len(state(engine, key)[1]) == (key != "cj")


def test_disable_is_audited_and_idempotent(engine: Engine) -> None:
    call(engine, "enable", "fx_frankfurter")
    assert call(engine, "disable", "fx_frankfurter") == {"changed": True}
    assert call(engine, "disable", "fx_frankfurter") == {"changed": False}
    source, events = state(engine, "fx_frankfurter")
    assert not source.enabled and source.status == "disabled"
    assert source.disabled_reason == "collector-cli" and source.disabled_at is not None
    assert [e.action for e in events] == ["enable", "disable"]


@pytest.mark.parametrize("op", ["enable", "disable"])
@pytest.mark.parametrize("key", ["backup", "nope", ""])
def test_unknown_source_refused(engine: Engine, op: str, key: str) -> None:
    with pytest.raises(ValueError, match="Unknown"):
        call(engine, op, key)
    assert not state(engine, "backup")[0].enabled


def test_seeds_repeat_safely_and_print_counts_only(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sources, "get_session", lambda: Session(engine))
    for changed in (3, 0):
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload())))
        assert sources.main(["seeds"]) == 0
        output = capsys.readouterr().out
        assert PRIVATE not in output
        assert json.loads(output) == {
            "changed": changed,
            "sources": {
                "shopify_stores": {"entries": 1, "enabled": 1},
                "cj": {"entries": 1, "enabled": 0},
                "google_trends": {"entries": 1, "enabled": 1},
            },
        }
    source, events = state(engine, "shopify_stores")
    assert source.config["seed"]["entries"][0]["domain"] == PRIVATE
    assert not source.enabled and events == []  # seeds never enable a source


def test_main_runs_source_ops(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sources, "get_session", lambda: Session(engine))
    assert sources.main(["enable", "fx_frankfurter"]) == 0
    assert json.loads(capsys.readouterr().out) == {"changed": True, "targets": None}
    assert sources.main(["disable", "fx_frankfurter"]) == 0
    assert json.loads(capsys.readouterr().out) == {"changed": True}
    with pytest.raises(ValueError):
        sources.main(["drop", "fx_frankfurter"])


# Data Health for `status` (data-05, DEC-210): fixture rows only.
SECRET = "https://fixture.test/rates?token=fixture-secret"


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def seed_health(session: Session, now: datetime) -> None:
    ids = dict(session.execute(select(Source.key, Source.id)).tuples().all())
    fx = session.get_one(Source, ids["fx_frankfurter"])
    fx.status, fx.retry_not_before, fx.disabled_reason = "blocked", DEADLINE, SECRET
    fx.config = {"seed": {"entries": [{"domain": PRIVATE}]}}
    session.add_all(
        [
            HostHeartbeat(host="ops-new", at=now - timedelta(seconds=90)),
            HostHeartbeat(host="ops-new", at=now - timedelta(hours=1)),
            HostHeartbeat(host="ops-old", at=now - timedelta(days=2)),
        ]
    )
    runs = [
        CollectorRun(
            source_id=fx.id,
            trigger="schedule",
            queued_at=now - timedelta(hours=hours),
            started_at=now - timedelta(hours=hours),
            finished_at=now - timedelta(hours=hours, minutes=-1),
            status=status,
            error_code=code,
            error_message=SECRET if code else None,
            params={"url": SECRET},
        )
        for hours, status, code in [
            (48, "success", None),
            (3, "success", None),
            (2, "failed", "http_429"),
        ]
    ]
    session.add_all(runs)
    session.flush()
    session.add_all(
        CollectionGap(
            source_id=fx.id,
            slot_key=f"fx:{days}",
            slot_start=now - timedelta(days=days),
            slot_end=now - timedelta(days=days - 1),
            reason="host_offline",
            filled_by_run_id=runs[0].id if days == 1 else None,  # the newest gap is filled
        )
        for days in (1, 2, 3)
    )


def check_health(result: dict[str, Any], now: datetime) -> None:
    assert [(b["host"], b["at"]) for b in result["heartbeats"]] == [
        ("ops-new", iso(now - timedelta(seconds=90))),
        ("ops-old", iso(now - timedelta(days=2))),
    ]
    assert 90 <= result["heartbeats"][0]["age_seconds"] < 150
    rows = {row["key"]: row for row in result.pop("sources")}
    assert list(rows) == sorted(rows) and set(sources.SOURCES) < set(rows)
    hour = timedelta(hours=1)
    assert rows.pop("fx_frankfurter") == {
        "key": "fx_frankfurter",
        "enabled": False,
        "status": "blocked",
        "retry_not_before": iso(DEADLINE),
        "latest_run": {
            "status": "failed",
            "started_at": iso(now - 2 * hour),
            "finished_at": iso(now - 2 * hour + timedelta(minutes=1)),
            "error_code": "http_429",
        },
        "runs_24h": {"failed": 1, "success": 1},
        "open_gaps": 2,
        "newest_open_gap": {
            "slot_key": "fx:2",
            "slot_start": iso(now - timedelta(days=2)),
            "slot_end": iso(now - timedelta(days=1)),
            "reason": "host_offline",
        },
    }
    for row in rows.values():
        assert (row["latest_run"], row["runs_24h"], row["open_gaps"]) == (None, {}, 0)
        assert row["newest_open_gap"] is None
    assert set(result) == {"as_of", "heartbeats"}
    # Codes, counts and times only: no config, error messages, params, URLs or settings.
    assert SECRET not in json.dumps(result) and PRIVATE not in json.dumps(result)


def test_health_reports_heartbeats_runs_and_open_gaps(engine: Engine) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session, session.begin():
        seed_health(session, now)
        result = sources.health(session)
    assert SECRET not in json.dumps(result) and PRIVATE not in json.dumps(result)
    check_health(result, now)


@pytest.mark.db
def test_health_main_runs_in_read_only_transaction(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    now = datetime.now(UTC)
    with Session(db_engine) as session, session.begin():
        seed_health(session, now)
    monkeypatch.setattr(sources, "get_session", lambda: Session(db_engine))
    assert sources.main(["health"]) == 0
    output = capsys.readouterr().out
    assert SECRET not in output and PRIVATE not in output
    check_health(json.loads(output), now)

    def write(session: Session) -> dict[str, Any]:
        session.add(HostHeartbeat(host="write-attempt"))
        session.flush()
        return {}

    monkeypatch.setattr(sources, "health", write)
    with pytest.raises(DBAPIError, match="read-only transaction"):
        sources.main(["health"])
    with Session(db_engine) as session:
        assert (
            session.scalar(select(HostHeartbeat).where(HostHeartbeat.host == "write-attempt"))
            is None
        )
