"""Temp checkout and fake subprocesses only; no Docker, sources or database access."""

import json
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

import backup
from collector import __main__ as host


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: p == repo / ".env.collector" or is_file(p))
    return repo


class Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.git = {"status": "", "branch": "main", "rev-list": "0"}
        self.running: list[str] = []
        self.failure = ""
        self.revisions: list[str] = []
        self.snapshot_open = False
        self.ndjson = False

    def __call__(self, args: list[str], cwd: Path, stdin: str | None) -> str:
        self.calls.append(args)
        if args[0] == "git":
            if args[1] == "status":
                assert args[2:] == ["--porcelain", "--untracked-files=no"]
            if args[1] == "rev-list":
                assert args[2:] == ["--count", "origin/main..HEAD"]
            return self.git.get(args[1], "")
        assert (cwd / ".git/pulso-collector-op.lock").is_dir()
        if self.failure and self.failure in args and (self.failure != "migrate" or "run" in args):
            raise RuntimeError("fixture failure; private subprocess output")
        if "ps" in args:
            rows = [
                {"Service": name, "State": "running", "Health": "healthy"} for name in self.running
            ]
            return "\n".join(map(json.dumps, rows)) if self.ndjson else json.dumps(rows)
        if "pg_dump" in args:
            assert self.snapshot_open and "-Fc" in args
        if "cp" in args:
            Path(args[-1]).write_bytes(b"PGDMP fixture")
        if "psql" in args:
            assert stdin == backup.REVISION  # Status never scans all table counts.
            return json.dumps({"server_version": "18", "alembic_version": self.revisions})
        return ""

    @contextmanager
    def snapshot(self, checkout: Path) -> Iterator[tuple[str, dict[str, object]]]:
        assert (checkout / ".git/pulso-collector-op.lock").is_dir()
        self.snapshot_open = True
        try:
            yield (
                "00000003-0000001B-1",
                {
                    "server_version": "18",
                    "alembic_version": self.revisions,
                    "row_counts": {},
                },
            )
        finally:
            self.snapshot_open = False


def invoke(checkout: Path, runner: Runner, op: str) -> None:
    host.execute(
        checkout, op, directory=checkout / "dumps", run=runner, open_snapshot=runner.snapshot
    )


@pytest.mark.parametrize("op", ["start", "update", "migrate", "status"])
@pytest.mark.parametrize("guard", ["dirty", "branch", "ahead", "hold", "lock", "linked"])
def test_guards_before_any_docker(checkout: Path, op: str, guard: str) -> None:
    runner = Runner()
    if guard in {"dirty", "branch", "ahead"}:
        runner.git[{"dirty": "status", "branch": "branch", "ahead": "rev-list"}[guard]] = "bad"
    elif guard == "linked":
        (checkout / ".git").rmdir()
        (checkout / ".git").write_text("gitdir: elsewhere", encoding="utf-8")
    elif guard == "hold":
        (checkout / ".collector-hold").touch()
    else:
        (checkout / ".git/pulso-collector-op.lock").mkdir()
    with pytest.raises(RuntimeError):
        invoke(checkout, runner, op)
    assert not any(c[0] == "docker" for c in runner.calls)


def test_collector_file_required(checkout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "is_file", lambda p: False)
    runner = Runner()
    with pytest.raises(RuntimeError, match="supply .env.collector"):
        invoke(checkout, runner, "start")
    assert not any(c[0] == "docker" for c in runner.calls)


@pytest.mark.parametrize("ndjson", [False, True])
def test_start_on_running_stack_is_noop(checkout: Path, ndjson: bool) -> None:
    runner = Runner()
    runner.running = host.INFRA + host.CONSUMERS
    runner.ndjson = ndjson
    invoke(checkout, runner, "start")
    assert [c[len(host.COMPOSE) :] for c in runner.calls if c[0] == "docker"] == [
        ["ps", "--all", "--format", "json"]
    ]


@pytest.mark.parametrize("op", ["start", "update", "migrate"])
def test_backup_before_migration_and_safe_resume(checkout: Path, op: str) -> None:
    runner = Runner()
    runner.running = ["postgres", "worker"]
    invoke(checkout, runner, op)
    calls = runner.calls
    build = next(i for i, c in enumerate(calls) if "build" in c)
    dump = next(i for i, c in enumerate(calls) if "pg_dump" in c)
    listed = next(i for i, c in enumerate(calls) if "--list" in c)
    copied = next(i for i, c in enumerate(calls) if "cp" in c)
    migration = next(i for i, c in enumerate(calls) if c[-1] == "migrate" and "run" in c)
    assert build < dump < listed < copied < migration
    assert calls[migration][-5:] == ["run", "--rm", "--no-deps", "-T", "migrate"]
    pulls = [c for c in calls if "pull" in c]
    assert pulls == ([["git", "pull", "--ff-only"]] if op == "update" else [])
    if pulls:
        assert calls.index(pulls[0]) < build
    resumed = ["worker"] if op == "migrate" else host.CONSUMERS
    assert calls[-1] == [*host.COMPOSE, "up", "-d", "--wait", *resumed]
    manifests = list((checkout / "dumps").glob("*.manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())["alembic_version"] == []
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert set(state) == {"op", "started", "finished", "exit", "log"}
    assert state["op"] == op and state["finished"] and state["exit"] == 0
    assert Path(state["log"]).is_file()
    assert not (checkout / ".git/pulso-collector-op.lock").exists()


@pytest.mark.parametrize("failure", ["build", "pg_dump", "--list", "cp", "migrate"])
def test_failed_step_aborts_and_preserves_stopped_consumers(checkout: Path, failure: str) -> None:
    runner = Runner()
    runner.failure = failure
    with pytest.raises(RuntimeError):
        invoke(checkout, runner, "migrate")
    if failure != "migrate":
        assert not any("run" in c and c[-1] == "migrate" for c in runner.calls)
    assert not any("up" in c and "worker" in c for c in runner.calls)
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert state["exit"] == 1 and state["finished"]
    assert "private subprocess output" not in Path(state["log"]).read_text()
    assert not (checkout / ".git/pulso-collector-op.lock").exists()


def test_status_reports_health_revision_and_previous_operation(
    checkout: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    runner.revisions = ["0002"]
    previous = {
        "op": "update",
        "exit": 0,
        "started": "fixture",
        "finished": "fixture",
        "log": "fixture",
    }
    backup.write_json(checkout / ".git/pulso-collector-op.json", previous)
    invoke(checkout, runner, "status")
    report = json.loads(capsys.readouterr().out.splitlines()[1])
    assert report == {
        "containers": [{"Service": "postgres", "State": "running", "Health": "healthy"}],
        "alembic_revision": ["0002"],
        "last_op": previous,
    }
    assert not any("build" in c or "run" in c or "up" in c for c in runner.calls)


def test_hold_created_mid_operation_stops_next_command(checkout: Path) -> None:
    runner = Runner()

    def run(args: list[str], cwd: Path, stdin: str | None) -> str:
        result = runner(args, cwd, stdin)
        if "build" in args:
            (checkout / ".collector-hold").touch()
        return result

    with pytest.raises(RuntimeError, match="hold"):
        host.execute(checkout, "start", run=run, open_snapshot=runner.snapshot)
    assert not any("stop" in c or "pg_dump" in c for c in runner.calls)


@pytest.mark.parametrize("op", ["start", "update", "migrate"])
def test_default_launch_is_detached_hidden_and_child_rechecks(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    op: str,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    checked: list[Path] = []
    monkeypatch.setattr(backup, "preflight", lambda path: checked.append(path))
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    assert host.main([op, "--checkout", str(checkout)]) == 0
    assert checked == [checkout]
    args, options = calls[0]
    assert args[1:] == [
        "-m",
        "infra.scripts.collector",
        op,
        "--checkout",
        str(checkout),
        "--execute",
    ]
    assert options["stdin"] == options["stdout"] == options["stderr"] == subprocess.DEVNULL
    assert (
        options["creationflags"] & subprocess.CREATE_NO_WINDOW
        if os.name == "nt"
        else options["start_new_session"]
    )
    monkeypatch.undo()
    # The child must reject a checkout that became dirty after the detached launch.
    (checkout / ".collector-hold").touch()
    assert host.main([op, "--checkout", str(checkout), "--execute"]) == 1


def test_lock_creation_race_does_not_replace_other_status(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mkdir = Path.mkdir
    status = checkout / ".git/pulso-collector-op.json"
    status.write_text('{"op":"other"}', encoding="utf-8")

    def competing_mkdir(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == "pulso-collector-op.lock":
            raise FileExistsError
        mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", competing_mkdir)
    with pytest.raises(RuntimeError, match="lock"):
        invoke(checkout, Runner(), "start")
    assert json.loads(status.read_text()) == {"op": "other"}


def test_forbidden_package_source() -> None:
    for path in Path(host.__file__).parent.glob("*.py"):
        source = path.read_text("utf-8").lower()
        for forbidden in ("down", "-v", "volume rm", "downgrade", "prune"):
            assert forbidden not in source, path


def test_empty_database_metadata_uses_psql_conditional() -> None:
    assert "to_regclass('public.alembic_version') IS NOT NULL" in backup.REVISION
    assert backup.REVISION.index("\\if :has_revision") < backup.REVISION.index(
        "FROM alembic_version"
    )
    assert "'alembic_version', '[]'::json" in backup.REVISION.split("\\else")[1]
    assert backup.parse_metadata('{"server_version":"18","alembic_version":[]}') == {
        "server_version": "18",
        "alembic_version": [],
        "row_counts": {},
    }
