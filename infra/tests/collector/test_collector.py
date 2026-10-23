"""Temp checkout and fake subprocesses only; no Docker, sources or database access."""

import json
import os
import subprocess
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import backup
from collector import __main__ as host

MERGES = "merge: P1-03b block accounting\nmerge: P1-38 and P1-39 fixes\nmerge: P1-09c trends"
OWNER_PATTERN = r"fixture-owner-status \d{4}-\d{2}-\d{2}"
OWNER_STATUS = "fixture-owner-status 2026-10-22"
LATER_OWNER_STATUS = "fixture-owner-status 2026-10-23"


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(host, "OWNER_STATUS_PATTERN", OWNER_PATTERN)
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: p == repo / ".env.collector" or is_file(p))
    return repo


class Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.git = {"status": "", "branch": "main", "rev-list": "0", "log": MERGES}
        self.running: list[str] = []
        self.failure = ""
        self.revisions: list[str] = []
        self.snapshot_open = False
        self.ndjson = False
        self.failing: set[str] = set()
        self.summary = "1 passed in 0.01s"
        self.container: dict[str, Any] = {"changed": True}
        self.stdin: list[str | None] = []

    def __call__(self, args: list[str], cwd: Path, stdin: str | None) -> str:
        self.calls.append(args)
        if args[0] == "git":
            if args[1] == "status":
                assert args[2:] == ["--porcelain", "--untracked-files=no"]
            if args[1] == "rev-list":
                assert args[2:] == ["--count", "origin/main..HEAD"]
            return self.git.get(args[1], "")
        assert (cwd / ".git/pulso-collector-op.lock").is_dir()
        if "pytest" in args:
            if self.failing & set(args):
                raise RuntimeError("python failed (exit 1); output withheld")
            return f"..\n{self.summary}"
        if host.CONTAINER[-1] in args:
            self.stdin.append(stdin)
            return f"Container noise\n{json.dumps(self.container)}"
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
        checkout,
        *op.split(),
        directory=checkout / "dumps",
        run=runner,
        open_snapshot=runner.snapshot,
    )


SOURCE_OPS = ["seeds", "enable fx_frankfurter", "enable cj", "disable cj"]


@pytest.mark.parametrize("op", ["start", "update", "migrate", "status", *SOURCE_OPS])
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


@pytest.mark.parametrize("op", ["start", "update", "migrate", *SOURCE_OPS])
def test_default_launch_is_detached_hidden_and_child_rechecks(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    op: str,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []
    checked: list[Path] = []
    monkeypatch.setattr(backup, "preflight", lambda path: checked.append(path))
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: calls.append((args, kw)))
    assert host.main([*op.split(), "--checkout", str(checkout)]) == 0
    assert checked == [checkout]
    args, options = calls[0]
    assert args[1:] == [
        "-m",
        "infra.scripts.collector",
        *op.split(),
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
    assert host.main([*op.split(), "--checkout", str(checkout), "--execute"]) == 1


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


# Seeds and source controls (P1-42, DEC-131): fixture evidence only.
PRIVATE = "owner-fixture.test"
SHIPPED_SEED = Path(__file__).resolve().parents[2] / "seeds/seed_v1.yaml"


def docs(
    checkout: Path,
    *,
    dec073: str = OWNER_STATUS,
    dec090: str = OWNER_STATUS,
    dec136: str = LATER_OWNER_STATUS,
    spk2: bool = True,
) -> None:
    (checkout / "docs").mkdir(exist_ok=True)
    (checkout / "docs/DECISIONS.md").write_text(
        f"### DEC-073 · Seeds\n**2026-10-22 · {dec073}** · x\n\n"
        f"### DEC-090 · SPK-3\n**2026-10-22 · {dec090}** · x\n\n"
        f"### DEC-136 · CJ\n**2026-10-23 · {dec136}** · x\n",
        encoding="utf-8",
    )
    spk = "### SPK-2 results (fixture)" if spk2 else "### SPK-2 command"
    (checkout / "docs/DATA_SOURCES.md").write_text(spk, encoding="utf-8")


def seed_files(checkout: Path, *, status: str = "approved", private: Sequence[str] = ()) -> None:
    text = SHIPPED_SEED.read_text(encoding="utf-8")
    data = json.loads("\n".join(x for x in text.splitlines() if not x.startswith("#")))
    approved_on = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    data["approval"].update(
        status=status, approved_on=approved_on if status == "approved" else None
    )
    data["stores"][0]["enabled"] = True
    (checkout / "infra/seeds").mkdir(parents=True)
    (checkout / "infra/seeds/seed_v1.yaml").write_text(json.dumps(data), encoding="utf-8")
    for i, body in enumerate(private):
        (checkout / f"infra/seeds/private-{i}.yaml").write_text(body, encoding="utf-8")


def owner_store(domain: str = PRIVATE) -> dict[str, object]:
    return {"domain": domain, "name": "Owner", "enabled": True}


def env_text(checkout: Path, monkeypatch: pytest.MonkeyPatch, text: str | None) -> None:
    read_text = Path.read_text

    def read(path: Path, *args: Any, **kwargs: Any) -> str:
        if path == checkout / ".env.collector":
            if text is None:
                raise FileNotFoundError("fixture-missing-env")
            return text
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)


def messages(checkout: Path) -> list[str]:
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    log = Path(state["log"]).read_text(encoding="utf-8")
    return [json.loads(line)["message"] for line in log.splitlines()]


def closed_gates(checkout: Path) -> set[str]:
    closed = [m.split(": ", 2)[2] for m in messages(checkout) if m.startswith("gate closed")]
    return {label.split(" -- ")[0] for label in closed}


def container_calls(runner: Runner) -> list[list[str]]:
    return [c for c in runner.calls if host.CONTAINER[-1] in c]


@pytest.mark.parametrize("dec", ["DEC-073", "DEC-090", "DEC-136"])
@pytest.mark.parametrize("pattern", [OWNER_PATTERN, ""])
@pytest.mark.parametrize(
    "status",
    [
        OWNER_STATUS,
        LATER_OWNER_STATUS,
        "approved (worker proposal)",
        "approved pending owner review",
        "proposed (P1-45)",
        "fixture-owner-status",
        "fixture-owner-status 2026-1-22",
        f"prefix {OWNER_STATUS}",
        f"{OWNER_STATUS} suffix",
        f" {OWNER_STATUS}",
        f"{OWNER_STATUS} ",
        "",
    ],
)
def test_owner_status_requires_exact_nonempty_grammar(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, dec: str, pattern: str, status: str
) -> None:
    monkeypatch.setattr(host, "OWNER_STATUS_PATTERN", pattern)
    docs(checkout, dec073=status, dec090=status, dec136=status)
    runner = Runner()
    expected = bool(pattern) and status in (OWNER_STATUS, LATER_OWNER_STATUS)
    assert host.passes(checkout, runner, "approved", (dec,)) is expected
    if dec == "DEC-073":
        seed_files(checkout)
        if expected:
            assert host.approved_seeds(checkout)
        else:
            with pytest.raises(RuntimeError, match="DEC-073"):
                host.approved_seeds(checkout)
    assert runner.calls == []


@pytest.mark.parametrize(
    ("text", "names"),
    [
        ("", set()),
        (
            "CJ_API_KEY=fixture-cj\nSERPAPI_API_KEY=fixture-trends",
            {"CJ_API_KEY", "SERPAPI_API_KEY"},
        ),
        ("CJ_API_KEY= \tfixture-cj # comment\r\nOTHER_2=x", {"CJ_API_KEY", "OTHER_2"}),
        ("CJ_API_KEY=\nSERPAPI_API_KEY=fixture-trends", {"SERPAPI_API_KEY"}),
        ("CJ_API_KEY= \t\r\nSERPAPI_API_KEY=fixture-trends", {"SERPAPI_API_KEY"}),
        ("CJ_API_KEY= # comment\nSERPAPI_API_KEY=\t# comment", set()),
        ("# CJ_API_KEY=x\n CJ_API_KEY=x\nexport CJ_API_KEY=x\ncj_api_key=x", set()),
    ],
)
def test_nonempty_env_names(text: str, names: set[str]) -> None:
    assert host.nonempty_env_names(text) == names


@pytest.mark.parametrize("source", ["cj", "google_trends"])
@pytest.mark.parametrize("text", [None, "", "CJ_API_KEY=\nSERPAPI_API_KEY= # comment", "present"])
def test_key_gates_use_names_only_and_never_emit_values(
    checkout: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    source: str,
    text: str | None,
) -> None:
    docs(checkout)
    runner = Runner()
    runner.running = ["postgres"]
    env_text(
        checkout,
        monkeypatch,
        "CJ_API_KEY=fixture-cj\nSERPAPI_API_KEY=fixture-trends" if text == "present" else text,
    )
    closed = set() if source == "cj" else {"owner-run OPEN-1/2 evidence"}
    if text != "present":
        closed.add("CJ_API_KEY" if source == "cj" else "SERPAPI_API_KEY")
    if closed:
        with pytest.raises(RuntimeError, match="step-4 gate"):
            invoke(checkout, runner, f"enable {source}")
        assert container_calls(runner) == []
    else:
        invoke(checkout, runner, f"enable {source}")
        assert container_calls(runner) == [[*host.COMPOSE, *host.CONTAINER, "enable", "cj"]]
    assert closed_gates(checkout) == closed
    output = capsys.readouterr()
    emitted = output.out + output.err + "\n".join(messages(checkout)) + repr(runner.calls)
    assert "fixture-cj" not in emitted and "fixture-trends" not in emitted


@pytest.mark.parametrize("evidence", ["missing", "empty owner grammar"])
def test_cj_agreement_refuses_missing_evidence(
    checkout: Path, monkeypatch: pytest.MonkeyPatch, evidence: str
) -> None:
    docs(checkout)
    if evidence == "missing":
        path = checkout / "docs/DECISIONS.md"
        path.write_text(path.read_text("utf-8").split("### DEC-136")[0], encoding="utf-8")
    if evidence == "empty owner grammar":
        monkeypatch.setattr(host, "OWNER_STATUS_PATTERN", "")
    env_text(checkout, monkeypatch, "CJ_API_KEY=fixture-cj")
    runner = Runner()
    with pytest.raises(RuntimeError, match="1 step-4 gate"):
        invoke(checkout, runner, "enable cj")
    assert closed_gates(checkout) == {"owner review of CJ's user agreement"}
    assert not any(c[0] == "docker" for c in runner.calls)


def break_gate(checkout: Path, runner: Runner, kind: str, args: tuple[str, ...]) -> None:
    if kind == "tests":
        runner.failing.add(args[-1])
    elif kind == "merged":
        runner.git["log"] = "\n".join(x for x in MERGES.splitlines() if args[-1] not in x)
    elif kind == "approved":
        docs(checkout, dec090="proposed")
    else:
        docs(checkout, spk2=False)


def test_fx_enable_runs_in_container_after_fixture_evidence(
    checkout: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    env_text(checkout, monkeypatch, "PG_PASSWORD=fixture-secret\n")
    invoke(checkout, runner, "enable fx_frankfurter")
    runner.container = {"changed": False, "targets": None}
    invoke(checkout, runner, "enable fx_frankfurter")  # repeat is a no-op in the container
    gates = host.GATES["fx_frankfurter"]
    assert closed_gates(checkout) == set()
    assert sum(m.startswith("gate open") for m in messages(checkout)) == len(gates)
    assert (
        container_calls(runner)
        == [[*host.COMPOSE, *host.CONTAINER, "enable", "fx_frankfurter"]] * 2
    )
    assert runner.stdin == [None, None]
    expected = {a for _, kind, args in gates if kind == "tests" for a in args}
    assert {a for c in runner.calls if "pytest" in c for a in c if "::" in a} == expected
    # The container's own env file selects the collector DB; nothing is passed or read here.
    docker = [c for c in runner.calls if c[0] == "docker"]
    assert not any({"-e", "--env"} & set(c) or "DATABASE_URL" in " ".join(c) for c in docker)
    output = capsys.readouterr()
    assert "fixture-secret" not in output.out + output.err + "\n".join(messages(checkout))
    state = json.loads((checkout / ".git/pulso-collector-op.json").read_text())
    assert state["op"] == "enable-fx_frankfurter" and state["exit"] == 0
    assert not (checkout / ".git/pulso-collector-op.lock").exists()


@pytest.mark.parametrize("gate", host.GATES["fx_frankfurter"], ids=lambda g: g[0])
def test_missing_fx_evidence_refuses_before_container(
    checkout: Path, gate: tuple[str, str, tuple[str, ...]]
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    break_gate(checkout, runner, gate[1], gate[2])
    with pytest.raises(RuntimeError, match="1 step-4 gate"):
        invoke(checkout, runner, "enable fx_frankfurter")
    assert closed_gates(checkout) == {gate[0]}
    assert container_calls(runner) == []
    assert json.loads((checkout / ".git/pulso-collector-op.json").read_text())["exit"] == 1


def test_skipped_tests_are_not_evidence(checkout: Path) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    runner.summary = "1 passed, 1 skipped in 0.01s"
    with pytest.raises(RuntimeError):
        invoke(checkout, runner, "enable fx_frankfurter")
    tests = {g[0] for g in host.GATES["fx_frankfurter"] if g[1] == "tests"}
    assert closed_gates(checkout) == tests and container_calls(runner) == []


CONDITION_E = "DEC-090 (e) no inventory-based labels"


@pytest.mark.parametrize(
    "gate", [g for g in host.GATES["shopify_stores"] if g[1] != "closed"], ids=lambda g: g[0]
)
def test_shopify_gates_fail_individually(
    checkout: Path, gate: tuple[str, str, tuple[str, ...]]
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    docs(checkout)
    break_gate(checkout, runner, gate[1], gate[2])
    with pytest.raises(RuntimeError, match="2 step-4 gate"):
        invoke(checkout, runner, "enable shopify_stores")
    assert closed_gates(checkout) == {gate[0], CONDITION_E}
    assert container_calls(runner) == []


@pytest.mark.parametrize(
    ("source", "closed"),
    [
        ("shopify_stores", {CONDITION_E}),
        ("google_trends", {"owner-run OPEN-1/2 evidence"}),
    ],
)
def test_unverifiable_gates_stay_closed_with_all_other_evidence(
    checkout: Path, source: str, closed: set[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    docs(checkout)
    env_text(checkout, monkeypatch, "CJ_API_KEY=fixture-cj\nSERPAPI_API_KEY=fixture-trends\n")
    with pytest.raises(RuntimeError, match="step-4 gate"):
        invoke(checkout, runner, f"enable {source}")
    assert closed_gates(checkout) == closed
    assert container_calls(runner) == []


def test_hold_created_during_gates_stops_before_container(checkout: Path) -> None:
    runner = Runner()
    runner.running = ["postgres"]

    def run(args: list[str], cwd: Path, stdin: str | None) -> str:
        result = runner(args, cwd, stdin)
        if "pytest" in args:
            (checkout / ".collector-hold").touch()
        return result

    with pytest.raises(RuntimeError):
        host.execute(checkout, "enable", "fx_frankfurter", run=run, open_snapshot=runner.snapshot)
    assert container_calls(runner) == [] and not any("ps" in c for c in runner.calls)


@pytest.mark.parametrize(
    "argv", [["enable"], ["disable"], ["enable", "backup"], ["disable", "nope"], ["start", "cj"]]
)
def test_invalid_or_unknown_source_refused(checkout: Path, argv: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        host.main([*argv, "--checkout", str(checkout), "--execute"])
    assert exit_info.value.code == 2
    runner = Runner()
    with pytest.raises(ValueError):
        host.execute(checkout, *argv, run=runner, open_snapshot=runner.snapshot)
    assert runner.calls == []


@pytest.mark.parametrize("op", SOURCE_OPS)
def test_source_ops_need_running_collector_postgres(
    checkout: Path, op: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = Runner()
    runner.running = ["redis", "worker"]
    docs(checkout)
    env_text(checkout, monkeypatch, "CJ_API_KEY=fixture-cj\n")
    seed_files(checkout)
    with pytest.raises(RuntimeError, match="Postgres is not running"):
        invoke(checkout, runner, op)
    assert container_calls(runner) == []


def test_disable_has_no_gates_and_container_refusal_fails(checkout: Path) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    invoke(checkout, runner, "disable shopify_stores")
    assert container_calls(runner) == [
        [*host.COMPOSE, *host.CONTAINER, "disable", "shopify_stores"]
    ]
    assert not any("pytest" in c for c in runner.calls)
    runner.container = {"refused": "blocked"}
    with pytest.raises(RuntimeError, match="blocked"):
        invoke(checkout, runner, "enable fx_frankfurter")
    assert "Refused: fx_frankfurter: blocked" in messages(checkout)


def test_seeds_send_approved_payload_on_stdin_and_log_counts_only(
    checkout: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    runner.container = {"changed": 3, "sources": {"shopify_stores": {"entries": 31, "enabled": 2}}}
    docs(checkout)
    seed_files(checkout, private=[f"# owner list\n{json.dumps({'stores': [owner_store()]})}"])
    invoke(checkout, runner, "seeds")
    invoke(checkout, runner, "seeds")  # the loader makes an identical repeat a no-op
    assert container_calls(runner) == [[*host.COMPOSE, *host.CONTAINER, "seeds"]] * 2
    assert runner.stdin[0] == runner.stdin[1]
    payload = json.loads(runner.stdin[0] or "")
    assert set(payload) == {"shopify_stores", "cj", "google_trends"}
    assert all(s["version"] == "seed_v1" and s["status"] == "approved" for s in payload.values())
    stores = payload["shopify_stores"]["entries"]
    assert len(stores) == 31 and stores[-1] == owner_store()
    assert not any("pytest" in c for c in runner.calls)
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err + "\n".join(messages(checkout))


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ({"status": "draft"}, "not approved seed_v1"),
        ({"dec073": "proposed"}, "DEC-073"),
        ({"private": ["{}", "{}"]}, "More than one"),
        ({"private": [json.dumps({"stores": [owner_store(), owner_store()]})]}, "withheld"),
        ({"private": [json.dumps({"stores": [owner_store()], "keys": []})]}, "withheld"),
        ({"private": [json.dumps({"stores": [owner_store("https://x.test/")]})]}, "withheld"),
        ({"private": [f'{{"stores": [{json.dumps(owner_store())}]']}, "withheld"),
    ],
)
def test_seeds_refuse_unapproved_or_invalid_files_before_docker(
    checkout: Path, capsys: pytest.CaptureFixture[str], setup: dict[str, Any], message: str
) -> None:
    runner = Runner()
    runner.running = ["postgres"]
    docs(checkout, dec073=setup.get("dec073", OWNER_STATUS))
    seed_files(checkout, status=setup.get("status", "approved"), private=setup.get("private", []))
    with pytest.raises(RuntimeError, match=message):
        invoke(checkout, runner, "seeds")
    assert not any(c[0] == "docker" for c in runner.calls)
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err + "\n".join(messages(checkout))
