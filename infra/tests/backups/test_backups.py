"""No Docker or database: real temporary Git checkouts and a fake process runner."""

import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import backup
import restore


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    backup.command(["git", "init", "-b", "main"], repo)
    (repo / "tracked").write_text("original", encoding="utf-8")
    backup.command(["git", "add", "tracked"], repo)
    backup.command(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "initial",
        ],
        repo,
    )
    backup.command(["git", "update-ref", "refs/remotes/origin/main", "HEAD"], repo)
    return repo


class FakeRunner:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.calls: list[list[str]] = []
        self.inputs: list[str] = []
        self.fail = ""
        self.rows = {"collector_runs": 7, "raw_payloads": 4, "listing_snapshots": 3}
        self.revisions = ["0002"]
        self.snapshot_open = False

    @contextmanager
    def snapshot(self, checkout: Path) -> Iterator[tuple[str, dict[str, object]]]:
        self.snapshot_open = True
        try:
            yield "00000003-0000001B-1", backup.metadata(checkout, "pulso", self)
        finally:
            self.snapshot_open = False

    def __call__(self, args: list[str], cwd: Path, stdin: str | None) -> str:
        if args[0] == "git":
            return backup.command(args, cwd, stdin)
        self.calls.append(args)
        assert args[: len(backup.COMPOSE)] == backup.COMPOSE
        if self.fail and self.fail in args:
            raise RuntimeError("fake process failure")
        if "pg_dump" in args:
            assert self.snapshot_open
            assert args[-2:] == ["--snapshot", "00000003-0000001B-1"]
        if "psql" in args:
            assert stdin is not None
            self.inputs.append(stdin)
            return "\n".join(
                json.dumps(row)
                for row in [
                    {"server_version": "18.3", "alembic_version": self.revisions},
                    *({"table": name, "count": count} for name, count in self.rows.items()),
                ]
            )
        if "cp" in args and args[-2] == "postgres:/tmp/pulso.dump":
            assert args[-1].endswith(".dump.partial")
            final = Path(args[-1]).with_suffix("")
            assert not final.exists()
            Path(args[-1]).write_bytes(b"PGDMP\x00\xff\r\nfixture")
            assert not final.exists()
        return ""


@pytest.mark.parametrize(
    "guard,message",
    [
        ("dirty", "dirty"),
        ("branch", "main"),
        ("ahead", "ahead"),
        ("hold", "hold"),
        ("lock", "lock"),
        ("linked", "primary checkout"),
    ],
)
@pytest.mark.parametrize("action", ["backup", "restore"])
def test_guards_before_any_docker_call(
    checkout: Path, tmp_path: Path, guard: str, message: str, action: str
) -> None:
    if guard == "dirty":
        (checkout / "tracked").write_text("changed", encoding="utf-8")
    elif guard == "branch":
        backup.command(["git", "checkout", "-b", "feature"], checkout)
    elif guard == "ahead":
        backup.command(
            [
                "git",
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-m",
                "ahead",
            ],
            checkout,
        )
    elif guard == "hold":
        (checkout / ".collector-hold").touch()
    elif guard == "lock":
        (checkout / ".git/pulso-collector-op.lock").mkdir()
    else:
        (checkout / ".git").rename(checkout / "git-original")
        (checkout / ".git").write_text("gitdir: git-original", encoding="utf-8")
    runner = FakeRunner(tmp_path)
    with pytest.raises(RuntimeError, match=message):
        if action == "backup":
            backup.backup(checkout, tmp_path, run=runner, open_snapshot=runner.snapshot)
        else:
            restore.restore(checkout, tmp_path, "pulso_restore_check", run=runner)
    assert runner.calls == []


def test_atomic_dump_manifest_snapshot_and_status(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = FakeRunner(tmp_path)
    rename = Path.rename

    def inspect_rename(path: Path, target: Path) -> Path:
        assert not target.exists()
        manifest = backup.Manifest.model_validate_json(
            target.with_suffix(".manifest.json").read_text()
        )
        assert manifest.sha256 == backup.checksum(path)
        assert manifest.coverage == "database only"
        assert manifest.raw_object_coverage == "none"
        assert manifest.row_counts == runner.rows
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", inspect_rename)
    (checkout / "untracked").touch()  # Deliberately ignored by the collector contract.
    dump = backup.backup(checkout, tmp_path, run=runner, open_snapshot=runner.snapshot)
    assert dump.read_bytes() == b"PGDMP\x00\xff\r\nfixture"
    assert not list(tmp_path.glob("*.partial"))
    assert runner.inputs == [backup.METADATA]
    assert not runner.snapshot_open
    assert any("pg_dump" in call for call in runner.calls)
    assert runner.calls.index(next(c for c in runner.calls if "--list" in c)) < runner.calls.index(
        next(c for c in runner.calls if "cp" in c)
    )
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert set(state) == {"op", "started", "finished", "exit", "log"}
    assert state["op"] == "backup" and state["exit"] == 0 and state["finished"]
    assert Path(state["log"]).is_file()
    assert not (checkout / ".git/pulso-collector-op.lock").exists()


@pytest.mark.parametrize("failure", ["psql", "pg_dump", "--list", "cp"])
def test_failed_dump_never_published(checkout: Path, tmp_path: Path, failure: str) -> None:
    runner = FakeRunner(tmp_path)
    runner.fail = failure
    with pytest.raises(RuntimeError):
        backup.backup(checkout, tmp_path, run=runner, open_snapshot=runner.snapshot)
    assert not runner.snapshot_open
    assert not list(tmp_path.glob("*.dump"))
    assert not list(tmp_path.glob("*.partial"))
    assert not (checkout / ".git/pulso-collector-op.lock").exists()
    assert json.loads((checkout / ".git/pulso-collector-op.json").read_text())["exit"] == 1
    if failure == "--list":
        assert not any("cp" in call for call in runner.calls)


def test_partial_copy_failure_is_removed(checkout: Path, tmp_path: Path) -> None:
    runner = FakeRunner(tmp_path)

    def broken_copy(args: list[str], cwd: Path, stdin: str | None) -> str:
        result = runner(args, cwd, stdin)
        if "cp" in args:
            raise RuntimeError("copy interrupted")
        return result

    with pytest.raises(RuntimeError, match="interrupted"):
        backup.backup(checkout, tmp_path, run=broken_copy, open_snapshot=runner.snapshot)
    assert not list(tmp_path.glob("pulso-*"))


def test_retention_daily_weekly_and_newest_three() -> None:
    now = datetime(2026, 10, 22, 12, tzinfo=UTC)
    paths = [
        Path(f"pulso-{(now - timedelta(days=i)).strftime(backup.STAMP)}.dump") for i in range(100)
    ]
    extras = [
        Path(f"pulso-{(now - timedelta(seconds=i)).strftime(backup.STAMP)}.dump") for i in (1, 2, 3)
    ]
    unknown = Path("pulso-not-a-date.dump")
    expired = set(backup.expired_dumps([*paths, *extras, unknown]))
    sundays = [p for p in paths if (stamp := backup.dump_time(p)) and stamp.weekday() == 6]
    expected = set(paths[:14] + sundays[:8] + extras[:2] + [unknown])
    assert set([*paths, *extras, unknown]) - expired == expected
    assert backup.expired_dumps(paths[:3]) == []


@pytest.mark.parametrize("delete", [False, True])
def test_retention_is_explicit_and_scoped(checkout: Path, tmp_path: Path, delete: bool) -> None:
    directory = tmp_path / "dumps"
    directory.mkdir()
    old = []
    for i in range(80):
        stamp = datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i)
        path = directory / f"pulso-{stamp.strftime(backup.STAMP)}.dump"
        path.touch()
        old.append(path)
    unrelated = [directory / "other.dump", directory / "pulso-bad.dump", tmp_path / old[0].name]
    for path in unrelated:
        path.touch()
    runner = FakeRunner(directory)
    latest = backup.backup(
        checkout, directory, delete_expired=delete, run=runner, open_snapshot=runner.snapshot
    )
    expired = backup.expired_dumps([*old, latest])
    assert all(path.exists() is not delete for path in expired)
    assert all(path.exists() for path in unrelated)
    assert latest.exists()
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert ("Retention delete:" if delete else "Retention would expire:") in Path(
        state["log"]
    ).read_text()


@pytest.mark.parametrize("success", [False, True])
def test_one_run_record_per_attempt_and_failure_preserves_dump(
    checkout: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, success: bool
) -> None:
    recorded: list[tuple[str, bool]] = []

    def record(url: str, started: datetime, ok: bool) -> None:
        assert started.tzinfo == UTC
        recorded.append((url, ok))
        raise RuntimeError("database unavailable: private diagnostic")

    monkeypatch.setattr(backup, "record_run", record)
    runner = FakeRunner(tmp_path)
    runner.fail = "" if success else "--list"
    if success:
        assert backup.backup(
            checkout, tmp_path, database_url="test-url", run=runner, open_snapshot=runner.snapshot
        ).exists()
    else:
        with pytest.raises(RuntimeError):
            backup.backup(
                checkout,
                tmp_path,
                database_url="test-url",
                run=runner,
                open_snapshot=runner.snapshot,
            )
    assert recorded == [("test-url", success)]
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert "private diagnostic" not in Path(state["log"]).read_text()


@pytest.mark.parametrize(
    "db,url",
    [
        ("pulso", None),
        ("postgres", None),
        ("pulso_restore_check;DROP", None),
        ("pulso_restore_check" + "x" * 64, None),
        ("pulso_restore_check", "postgresql+psycopg://localhost/pulso_restore_check"),
    ],
)
def test_restore_target_guard_before_any_process(tmp_path: Path, db: str, url: str | None) -> None:
    runner = FakeRunner(tmp_path)
    with pytest.raises(RuntimeError, match="Target"):
        restore.restore(tmp_path, tmp_path, db, database_url=url, run=runner)
    assert runner.calls == []


@pytest.mark.parametrize(
    "failure", ["", "createdb", "--dbname", "row_counts", "revision", "checksum"]
)
def test_restore_latest_compares_and_cleans_only_its_database(
    checkout: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str], failure: str
) -> None:
    runner = FakeRunner(tmp_path)
    dump = backup.backup(checkout, tmp_path, run=runner, open_snapshot=runner.snapshot)
    (tmp_path / "pulso-20991231T235959000000Z.dump.partial").touch()
    runner.calls.clear()
    runner.fail = failure if failure in {"createdb", "--dbname"} else ""
    if failure == "row_counts":
        runner.rows["collector_runs"] += 1
    if failure == "revision":
        runner.revisions = ["unexpected"]
    if failure == "checksum":
        dump.write_bytes(b"corrupt")
    if failure:
        with pytest.raises(RuntimeError):
            restore.restore(checkout, tmp_path, "pulso_restore_check_test", run=runner)
    else:
        restore.restore(checkout, tmp_path, "pulso_restore_check_test", run=runner)
    drops = [c for c in runner.calls if "dropdb" in c]
    assert len(drops) == (0 if failure in {"createdb", "checksum"} else 1)
    assert all(c[-1] == "pulso_restore_check_test" for c in drops)
    assert dump.exists()
    if failure == "checksum":
        assert runner.calls == []
    else:
        assert str(dump) in next(c for c in runner.calls if "cp" in c)
        assert "raw-object checks (BAK-2 R-11) are a later task" in capsys.readouterr().out


def test_record_run_uses_existing_backup_source(monkeypatch: pytest.MonkeyPatch) -> None:
    from unittest.mock import MagicMock

    engine = MagicMock()
    session = MagicMock()
    session.__enter__.return_value = session
    session.scalar.return_value = 42
    monkeypatch.setattr(backup, "make_engine", lambda url: engine)
    monkeypatch.setattr(backup, "Session", lambda instance: session)
    backup.record_run("test-url", datetime.now(UTC), True)
    row = session.add.call_args.args[0]
    assert row.source_id == 42 and row.status == "success" and row.complete is True
    assert session.scalar.call_args.args[0].compile().params == {"key_1": "backup"}
    engine.dispose.assert_called_once()


def test_detached_launch_is_hidden_and_rechecks_in_child(
    checkout: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def launch(args: list[str], **kwargs: Any) -> None:
        assert "--detach" not in args
        calls.append(kwargs)

    monkeypatch.setattr(
        sys, "argv", [str(Path(backup.__file__)), "--checkout", str(checkout), "--detach"]
    )
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(backup, "preflight", lambda path: None)
    backup.detach(checkout)
    assert calls[0]["stdin"] == subprocess.DEVNULL
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
        assert calls[0]["creationflags"] == flags
    else:
        assert calls[0]["start_new_session"] is True
        assert calls[0]["creationflags"] == 0


def test_forbidden_script_strings() -> None:
    for module in (backup, restore):
        assert module.__file__ is not None
        source = Path(module.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("down", "-v", "volume rm", "downgrade", "prune"):
            assert forbidden not in source


@pytest.mark.parametrize("failure", ["", "token", "counts", "session", "dump"])
def test_snapshot_transaction_stays_open_through_dump_and_always_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    from unittest.mock import MagicMock

    process = MagicMock()
    process.__enter__.return_value = process
    process.stdin = io.StringIO()
    output = (
        "00000003-0000001B-1\n"
        + json.dumps({"server_version": "18.3", "alembic_version": ["0002"]})
        + '\n{"table":"collector_runs","count":7}\nREADY\n'
    )
    if failure == "token":
        output = "bad token\n"
    if failure == "counts":
        output = output.replace("READY\n", "")
    process.stdout = io.StringIO(output)
    process.returncode = 1 if failure == "session" else 0
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)

    def exercise() -> None:
        with backup.snapshot(tmp_path) as (token, details):
            process.communicate.assert_not_called()
            assert "pg_export_snapshot()" in process.stdin.getvalue()
            assert "REPEATABLE READ READ ONLY" in process.stdin.getvalue()
            assert token == "00000003-0000001B-1"
            assert details["row_counts"] == {"collector_runs": 7}
            if failure == "dump":
                raise RuntimeError("dump failed")

    if failure:
        with pytest.raises(RuntimeError):
            exercise()
    else:
        exercise()
    process.communicate.assert_called_once_with("ROLLBACK;\n", timeout=10)
