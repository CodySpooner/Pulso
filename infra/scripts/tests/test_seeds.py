import json
from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import JSON, MetaData, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_sources.seed_approval import SEED_SOURCES, approved_targets
from seeds import __main__ as cli
from seeds import load_seeds, read_seed

SEEDS = Path(__file__).resolve().parents[2] / "seeds/seed_v1.yaml"


def shipped_seed() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        "\n".join(
            line
            for line in SEEDS.read_text(encoding="utf-8").splitlines()
            if not line.startswith("#")
        )
    )
    return data


@pytest.fixture
def seed_data() -> dict[str, Any]:
    """A draft, all-disabled copy of the shipped list (which is approved, DEC-073)."""
    data = shipped_seed()
    data["approval"].update(status="draft", approved_on=None)
    for section in SEED_SOURCES:
        for row in data[section]:
            row["enabled"] = False
    return data


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")
    table = Source.metadata.tables["sources"].to_metadata(MetaData())
    table.c.config.type = JSON()
    table.c.config.server_default = None
    table.create(engine)
    with Session(engine) as session, session.begin():
        for i, key in enumerate([*SEED_SOURCES.values(), "fx_frankfurter"], 1):
            session.add(
                Source(
                    id=i,
                    key=key,
                    name=key,
                    type="api",
                    phase=1,
                    enabled=i % 2 == 0,
                    config={"expected_interval": 86400},
                )
            )
    yield engine
    engine.dispose()


def write_seed(tmp_path: Path, data: dict[str, Any]) -> Path:
    path = tmp_path / "fixture.yaml"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_cli_preview_has_counts_without_writes(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_session", lambda: Session(engine))
    cli.main([])
    output = capsys.readouterr().out
    for key, count in zip(SEED_SOURCES.values(), (30, 10, 50), strict=True):
        assert f"{key}: {count} entries, {count} enabled" in output
        assert f"+++ {key}.config.seed (proposed)" in output
    assert "Dry run" in output
    with Session(engine) as session:
        assert all(
            s.config == {"expected_interval": 86400} for s in session.scalars(select(Source))
        )


def test_cli_apply_is_idempotent_and_preserves_source_flags_and_config(
    engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "get_session", lambda: Session(engine))
    cli.main(["--apply"])
    assert "Applied: 3 source(s) changed" in capsys.readouterr().out
    with engine.connect() as connection:
        before = connection.exec_driver_sql("SELECT total_changes()").scalar_one()
    cli.main(["--apply"])
    assert "Applied: 0 source(s) changed" in capsys.readouterr().out
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT total_changes()").scalar_one() == before
    with Session(engine) as session:
        for source in session.scalars(select(Source)):
            assert source.enabled is (source.id % 2 == 0)
            assert source.config["expected_interval"] == 86400
            if source.key == "fx_frankfurter":
                assert "seed" not in source.config
            else:
                assert source.config["seed"]["version"] == "seed_v1"
                assert all(row["enabled"] for row in source.config["seed"]["entries"])


@pytest.mark.parametrize("approved", [False, True])
def test_guard_only_returns_enabled_approved_targets(
    engine: Engine,
    seed_data: dict[str, Any],
    tmp_path: Path,
    approved: bool,
) -> None:
    if approved:
        seed_data["approval"].update(status="approved", approved_on="2026-10-22")
    for section in SEED_SOURCES:
        seed_data[section][0]["enabled"] = True
    seeds = read_seed(write_seed(tmp_path, seed_data))
    with Session(engine) as session, session.begin():
        load_seeds(session, seeds, apply=True)
    with Session(engine) as session:
        for section, key in SEED_SOURCES.items():
            targets = approved_targets(session, key)
            assert targets == ([seed_data[section][0]] if approved else [])
        assert approved_targets(session, "fx_frankfurter") == []
        assert approved_targets(session, "unknown") == []


def test_shipped_approval_matches_existing_decision_evidence() -> None:
    seed_data = shipped_seed()
    approval = seed_data["approval"]
    if approval["status"] != "approved":
        assert approval["status"] == "draft"
        assert approval["approved_on"] is None
        assert not any(row["enabled"] for section in SEED_SOURCES for row in seed_data[section])
        return
    decisions = (SEEDS.parents[2] / "docs/DECISIONS.md").read_text(encoding="utf-8")
    rows = decisions.splitlines()
    evidence = next(row for row in rows if row.startswith("| DEC-073 |"))
    recorded_status = evidence.split("|")[3].strip()
    assert recorded_status.startswith("approved ")
    assert approval["approved_on"] == recorded_status.rsplit(" ", 1)[1]
    index = next(row for row in rows if row.startswith("| DEC-011 |"))
    entry = decisions.split("### DEC-011 ", 1)[1].split("\n### ", 1)[0]
    assert recorded_status in index and recorded_status in entry.splitlines()[1]
    evidence_entry = decisions.split("### DEC-073 ", 1)[1].split("\n### ", 1)[0]
    assert f"`{approval['version']}`" in evidence_entry


@pytest.mark.parametrize(
    ("original", "duplicate"),
    [
        ('"enabled": false', '"enabled": false, "enabled": true'),
        ('"enabled": false', '"enabled": true, "enabled": false'),
        ('"approval": {', '"approval": {}, "approval": {'),
        ('"status": "draft"', '"status": "approved", "status": "draft"'),
    ],
)
def test_duplicate_json_keys_rejected(
    seed_data: dict[str, Any], tmp_path: Path, original: str, duplicate: str
) -> None:
    path = write_seed(tmp_path, seed_data)
    path.write_text(json.dumps(seed_data).replace(original, duplicate, 1), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        read_seed(path)


@pytest.mark.parametrize("days_ahead", [0, 1])
def test_approval_date_is_bounded_by_today_utc(
    engine: Engine, seed_data: dict[str, Any], tmp_path: Path, days_ahead: int
) -> None:
    approved_on = (datetime.now(UTC).date() + timedelta(days=days_ahead)).isoformat()
    seed_data["approval"].update(status="approved", approved_on=approved_on)
    seed_data["stores"][0]["enabled"] = True
    path = write_seed(tmp_path, seed_data)
    if days_ahead:
        with pytest.raises(ValueError, match="approved_on"):
            read_seed(path)
    else:
        assert read_seed(path)["shopify_stores"]["entries"][0]["enabled"] is True
    with Session(engine) as session, session.begin():
        source = session.get_one(Source, 1)
        source.config = {"seed": {**seed_data["approval"], "entries": seed_data["stores"]}}
        assert approved_targets(session, source.key) == (
            [] if days_ahead else seed_data["stores"][:1]
        )


@pytest.mark.parametrize(
    "domain",
    [
        "https://store.example",
        "store.example/path",
        "bad..example",
        "-bad.example",
        "bad-.example",
        "localhost",
        "127.0.0.1",
        "store.example:443",
        "store.example.",
        "store_example.com",
        "store.example?x=1",
        "user@store.example",
    ],
)
def test_invalid_domains_fail_clearly(
    seed_data: dict[str, Any],
    tmp_path: Path,
    domain: str,
) -> None:
    seed_data["stores"][0]["domain"] = domain
    with pytest.raises(ValueError, match=r"stores\[0\].domain.*domain"):
        read_seed(write_seed(tmp_path, seed_data))


def test_domains_normalize_and_normalized_duplicates_fail(
    seed_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    seed_data["stores"][0]["domain"] = " SAGEANDSILL.COM "
    seeds = read_seed(write_seed(tmp_path, seed_data))
    assert seeds["shopify_stores"]["entries"][0]["domain"] == "sageandsill.com"
    seed_data["stores"][1]["domain"] = "sageandsill.com"
    with pytest.raises(ValueError, match="duplicate domain: sageandsill.com"):
        read_seed(write_seed(tmp_path, seed_data))


def test_keywords_are_unique_ignoring_case_and_whitespace(
    seed_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    seed_data["keywords"][1]["keyword"] = "  CAT   TREE "
    with pytest.raises(ValueError, match="duplicate keyword: cat tree"):
        read_seed(write_seed(tmp_path, seed_data))


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("stores", "name", ""),
        ("stores", "enabled", "true"),
        ("cj_categories", "name", None),
        ("keywords", "geo", "GB"),
        ("keywords", "tz", False),
        ("keywords", "tz", 60),
    ],
)
def test_required_entry_fields(
    seed_data: dict[str, Any],
    tmp_path: Path,
    section: str,
    field: str,
    value: Any,
) -> None:
    seed_data[section][0][field] = value
    with pytest.raises(ValueError, match=rf"{section}\[0\].{field}"):
        read_seed(write_seed(tmp_path, seed_data))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "ready"),
        ("approved_on", "2026-02-30"),
        ("decision", "DEC-999"),
        ("version", ""),
    ],
)
def test_bad_approval_metadata(
    seed_data: dict[str, Any],
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    seed_data["approval"][field] = value
    with pytest.raises(ValueError, match="approval"):
        read_seed(write_seed(tmp_path, seed_data))


def test_approved_requires_date(seed_data: dict[str, Any], tmp_path: Path) -> None:
    seed_data["approval"]["status"] = "approved"
    with pytest.raises(ValueError, match="approved_on"):
        read_seed(write_seed(tmp_path, seed_data))


@pytest.mark.parametrize("section", ["approval", *SEED_SOURCES])
def test_missing_section_fails(seed_data: dict[str, Any], tmp_path: Path, section: str) -> None:
    del seed_data[section]
    with pytest.raises(ValueError, match=section):
        read_seed(write_seed(tmp_path, seed_data))


def test_unknown_section_rejected(seed_data: dict[str, Any], tmp_path: Path) -> None:
    seed_data["unknown_source"] = []
    with pytest.raises(ValueError, match="unknown_source"):
        read_seed(write_seed(tmp_path, seed_data))


@pytest.mark.parametrize(
    "seed",
    [
        None,
        {},
        {"status": "approved"},
        {
            "version": "seed_v1",
            "status": "approved",
            "approved_on": "invalid",
            "decision": "DEC-011",
        },
        {
            "version": "seed_v1",
            "status": "draft",
            "approved_on": None,
            "decision": "DEC-011",
            "entries": [{"enabled": True}],
        },
    ],
)
def test_guard_fails_closed_for_missing_or_bad_metadata(engine: Engine, seed: Any) -> None:
    with Session(engine) as session, session.begin():
        source = session.get_one(Source, 1)
        source.config = {"seed": seed}
        assert approved_targets(session, source.key) == []


def test_changed_version_replaces_only_seed_and_same_version_conflict_is_atomic(
    engine: Engine,
    seed_data: dict[str, Any],
    tmp_path: Path,
) -> None:
    with Session(engine) as session, session.begin():
        load_seeds(session, read_seed(SEEDS), apply=True)
    seed_data["keywords"][0]["keyword"] = "different keyword"
    with Session(engine) as session, pytest.raises(ValueError, match="bump.*version"):
        load_seeds(session, read_seed(write_seed(tmp_path, seed_data)), apply=True)
        session.commit()
    seed_data["approval"]["version"] = "seed_v2"
    with Session(engine) as session, session.begin():
        assert load_seeds(session, read_seed(write_seed(tmp_path, seed_data)), apply=True) == 3
    with Session(engine) as session:
        source = session.get_one(Source, 3)
        assert source.config["seed"]["entries"][0]["keyword"] == "different keyword"
        assert source.config["expected_interval"] == 86400


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize(
    ("installed", "incoming"), [("seed_v2", "seed_v1"), ("seed_v10", "seed_v9")]
)
def test_older_revision_is_rejected_before_any_source_changes(
    engine: Engine,
    seed_data: dict[str, Any],
    tmp_path: Path,
    apply: bool,
    installed: str,
    incoming: str,
) -> None:
    seed_data["approval"]["version"] = installed
    seeds = read_seed(write_seed(tmp_path, seed_data))
    with Session(engine) as session, session.begin():
        # Put the newer revision last so earlier sources would otherwise be changed first.
        source = session.get_one(Source, 3)
        source.config = {**source.config, "seed": seeds[source.key]}
    seed_data["approval"]["version"] = incoming
    seeds = read_seed(write_seed(tmp_path, seed_data))
    with Session(engine) as session, session.begin():
        before = [(s.enabled, deepcopy(s.config)) for s in session.scalars(select(Source))]
        with pytest.raises(ValueError, match="older seed version"):
            load_seeds(session, seeds, apply=apply)
        assert not session.dirty
        assert [(s.enabled, s.config) for s in session.scalars(select(Source))] == before


def test_missing_source_rolls_back_whole_load(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        session.delete(session.get_one(Source, 3))
    with Session(engine) as session, pytest.raises(ValueError, match="google_trends"):
        with session.begin():
            load_seeds(session, read_seed(SEEDS), apply=True)
    with Session(engine) as session:
        assert all("seed" not in source.config for source in session.scalars(select(Source)))


@pytest.mark.parametrize("entries", [None, {}, [{"enabled": "true"}, {"enabled": 1}, {}]])
def test_guard_rejects_malformed_targets(engine: Engine, entries: Any) -> None:
    with Session(engine) as session, session.begin():
        source = session.get_one(Source, 1)
        source.config = {
            "seed": {
                "version": "seed_v1",
                "status": "approved",
                "approved_on": "2026-10-22",
                "decision": "DEC-011",
                "entries": entries,
            }
        }
        assert approved_targets(session, source.key) == []


@pytest.mark.parametrize(
    ("section", "bad_entry"),
    [
        ("stores", {"enabled": True}),
        ("stores", {"domain": "http://127.0.0.1:8080/admin", "name": "Bad", "enabled": True}),
        ("stores", {"domain": "127.0.0.1", "name": "Bad", "enabled": True}),
        ("stores", {"domain": "store.example", "name": "", "enabled": True}),
        ("cj_categories", {"name": None, "enabled": True}),
        ("cj_categories", {"name": "Pet Supplies", "enabled": "true"}),
        ("keywords", {"keyword": "cat tree", "geo": "GB", "tz": 0, "enabled": True}),
        ("keywords", {"keyword": "cat tree", "geo": "US", "tz": False, "enabled": True}),
        ("keywords", {"keyword": "cat tree", "geo": "US", "tz": 60, "enabled": False}),
    ],
)
def test_guard_validates_all_stored_entries(
    engine: Engine, seed_data: dict[str, Any], section: str, bad_entry: dict[str, Any]
) -> None:
    with Session(engine) as session, session.begin():
        source = session.scalar(select(Source).where(Source.key == SEED_SOURCES[section]))
        assert source is not None
        good = {**seed_data[section][0], "enabled": True}
        source.config = {
            "seed": {
                **seed_data["approval"],
                "status": "approved",
                "approved_on": "2026-10-22",
                "entries": [good, bad_entry],
            }
        }
        before = deepcopy(source.config)
        assert approved_targets(session, source.key) == []
        assert source.config == before


@pytest.mark.parametrize("section", SEED_SOURCES)
def test_guard_rejects_duplicate_stored_entries(
    engine: Engine, seed_data: dict[str, Any], section: str
) -> None:
    with Session(engine) as session, session.begin():
        source = session.scalar(select(Source).where(Source.key == SEED_SOURCES[section]))
        assert source is not None
        row = {**seed_data[section][0], "enabled": True}
        source.config = {
            "seed": {
                **seed_data["approval"],
                "status": "approved",
                "approved_on": "2026-10-22",
                "entries": [row, dict(row)],
            }
        }
        assert approved_targets(session, source.key) == []


def test_guard_normalizes_copies_without_changing_stored_entries(engine: Engine) -> None:
    with Session(engine) as session, session.begin():
        source = session.get_one(Source, 1)
        row = {"domain": " STORE.EXAMPLE ", "name": "Store", "enabled": True}
        source.config = {
            "seed": {
                "version": "seed_v1",
                "status": "approved",
                "approved_on": "2026-10-22",
                "decision": "DEC-011",
                "entries": [row],
            }
        }
        targets = approved_targets(session, source.key)
        assert targets == [{**row, "domain": "store.example"}]
        targets[0]["enabled"] = False
        assert source.config["seed"]["entries"] == [row]
        assert row == {"domain": " STORE.EXAMPLE ", "name": "Store", "enabled": True}


@pytest.mark.parametrize(
    "error",
    [
        SQLAlchemyError("sensitive fixture value"),
        ValidationError.from_exception_data(
            "Settings",
            [
                {"type": "int_parsing", "loc": ("port",), "input": "sensitive fixture value"},
            ],
        ),
    ],
)
def test_cli_does_not_print_database_or_settings_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    def unavailable_session() -> Session:
        raise error

    monkeypatch.setattr(cli, "get_session", unavailable_session)
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    output = capsys.readouterr().err
    assert "worktree" in output
    assert "sensitive fixture value" not in output


def test_invalid_file_fails_before_opening_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def unexpected_session() -> Session:
        pytest.fail("Invalid seed must not open a database session")

    monkeypatch.setattr(cli, "get_session", unexpected_session)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--seed-file", str(write_seed(tmp_path, {})), "--apply"])
    assert exc.value.code == 2
    assert "missing" in capsys.readouterr().err
