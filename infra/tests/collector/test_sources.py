"""In-container seeds/enable/disable logic against in-memory SQLite; no collector DB."""

import io
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from collector import sources
from pulso_core.models import Source, SourceEvent

PRIVATE = "owner-fixture.test"
DEADLINE = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.fixture
def engine() -> Iterator[Engine]:
    metadata = MetaData()
    engine = create_engine("sqlite://")
    for name in ("sources", "source_events"):
        table = Source.metadata.tables[name].to_metadata(metadata)
        for column in table.columns:
            if column.name == "id" and name == "source_events":
                column.type = Integer()  # SQLite autoincrements only INTEGER keys
            if column.name == "config":
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
