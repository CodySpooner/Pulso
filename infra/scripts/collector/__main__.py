"""Run from the repo root: uv run --frozen python -m infra.scripts.collector OP [SOURCE]."""

import argparse
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

# P1-14 is also a direct script; both entry points use its existing import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup  # noqa: E402
from pulso_sources.seed_approval import validate_seed_entries  # noqa: E402
from seeds import _unique_object, read_seed  # noqa: E402

COMPOSE = [*backup.COMPOSE, "--profile", "collector"]
INFRA = ["postgres", "redis", "s3"]
CONSUMERS = ["beat", "worker", "worker-ops"]
# One-shot container from the stack's worker image; its env file selects the collector DB.
CONTAINER = [
    "run",
    "--rm",
    "--no-deps",
    "-T",
    "worker",
    "python",
    "-m",
    "infra.scripts.collector.sources",
]

# Lead Playbook §6 step 4 evidence (DEC-131). Kinds: tests (pass at this clean main checkout),
# merged (a "merge: <task>" commit in HEAD), approved (DEC status line), doc (marker in a repo
# file), closed (evidence this command cannot verify). Seed sources also need approved targets,
# checked in the container. No flag skips a gate.
Gate = tuple[str, str, tuple[str, ...]]
TESTS = "packages/sources/tests/"
BLOCK = f"{TESTS}framework/test_block_retry.py::"
SHOPIFY = f"{TESTS}shopify_stores/test_catalog.py::"
COMMON: list[Gate] = [
    ("P1-03b merged", "merged", ("P1-03b",)),
    (
        "block tests: one disable event, Retry-After honoured",
        "tests",
        (
            f"{BLOCK}test_blocks_stop_plan_and_disable_once_across_runs",
            f"{BLOCK}test_retry_deadline_is_atomic_and_respected_across_runs",
        ),
    ),
    (
        "global 30/min limiter test",
        "tests",
        (f"{SHOPIFY}test_configured_global_budget_and_robots_delay",),
    ),
]
REVIEW_FIXES: Gate = ("P1-37 M1/M2 fixes merged (P1-38, P1-39)", "merged", ("P1-38", "P1-39"))
NO_KEY = ("never inspected here; the Playbook key-name check does not list it",)
GATES: dict[str, list[Gate]] = {
    "fx_frankfurter": [
        *COMMON,
        (
            "parse() fixture tests",
            "tests",
            tuple(
                f"{TESTS}fx_frankfurter/test_fx.py::{name}"
                for name in ("test_parse_fixture", "test_invalid_payload")
            ),
        ),
    ],
    "shopify_stores": [
        *COMMON,
        ("parse() fixture tests", "tests", (f"{SHOPIFY}test_parse_every_saved_fixture",)),
        (
            "SPK-2 results in docs/DATA_SOURCES.md",
            "doc",
            ("docs/DATA_SOURCES.md", "### SPK-2 results"),
        ),
        ("SPK-3 owner go: DEC-090 approved", "approved", ("DEC-090",)),
        (
            "DEC-090 (a) per-store spacing above 3 s",
            "tests",
            (
                f"{SHOPIFY}test_limiter_user_agent_and_no_retry",
                f"{TESTS}shopify_stores/test_review_fixes.py::"
                "test_run_seeds_spacing_from_captures_after_clock_reset",
            ),
        ),
        (
            "DEC-090 (b) no repeated URL in a run",
            "tests",
            (
                f"{SHOPIFY}test_complete_store_isolated_from_page_two_failure",
                f"{SHOPIFY}test_two_pages_then_304_refreshes_without_snapshots",
            ),
        ),
        (
            "DEC-090 (c) robots.txt redirect not followed",
            "tests",
            (f"{SHOPIFY}test_untrackable_or_robots_failure_never_completes[robots_redirect]",),
        ),
        (
            "DEC-090 (d) first block stops the run",
            "tests",
            (
                f"{SHOPIFY}test_blocks_stop_run_and_persist_retry_floor",
                f"{SHOPIFY}test_fatal_430_disables_once",
                f"{SHOPIFY}test_five_429_runs_disable_and_same_slot_delivery_is_noop",
            ),
        ),
        (
            "DEC-090 (e) no inventory-based labels",
            "closed",
            ("no fixture test proves Grade A labels are unavailable",),
        ),
        REVIEW_FIXES,
    ],
    "cj": [
        *COMMON,
        (
            "parse() fixture tests",
            "tests",
            tuple(
                f"{TESTS}cj/test_cj.py::{name}"
                for name in ("test_catalog_and_empty_parse", "test_invalid_money_fails")
            ),
        ),
        REVIEW_FIXES,
        ("owner review of CJ's user agreement", "closed", ("no approved DEC yet",)),
        ("CJ_API_KEY", "closed", NO_KEY),
    ],
    "google_trends": [
        *COMMON,
        (
            "parse() fixture tests",
            "tests",
            tuple(
                f"{TESTS}google_trends/test_trends.py::{name}"
                for name in ("test_parse", "test_invalid_values", "test_invalid_partial_flag")
            ),
        ),
        ("P1-09c live transport merged", "merged", ("P1-09c",)),
        ("owner-run OPEN-1/2 evidence", "closed", ("not recorded",)),
        ("SERPAPI_API_KEY", "closed", NO_KEY),
    ],
}
SOURCES = tuple(GATES)


def containers(checkout: Path, run: backup.Runner) -> list[dict[str, Any]]:
    output = run([*COMPOSE, "ps", "--all", "--format", "json"], checkout, None)
    rows = (
        json.loads(output)
        if output.startswith("[")
        else [json.loads(line) for line in output.splitlines()]
    )
    return [{key: row.get(key, "") for key in ("Service", "State", "Health")} for row in rows]


def comments_stripped(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def dec_status(checkout: Path, dec: str) -> str:
    text = (checkout / "docs/DECISIONS.md").read_text(encoding="utf-8")
    match = re.search(rf"^### {dec} .*\n\*\*\d{{4}}-\d{{2}}-\d{{2}} · ([^*]+)\*\*", text, re.M)
    return match[1] if match else ""


def passes(checkout: Path, run: backup.Runner, kind: str, args: tuple[str, ...]) -> bool:
    if kind == "tests":
        pytest = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args]
        last = run(pytest, checkout, None).rpartition("\n")[2]
        return re.fullmatch(r"\d+ passed(, \d+ warnings?)? in .+", last) is not None  # no skips
    if kind == "merged":
        subjects = run(["git", "log", "--merges", "--format=%s", "HEAD"], checkout, None)
        return all(re.search(rf"^merge: .*\b{re.escape(t)}\b", subjects, re.M) for t in args)
    if kind == "approved":
        return dec_status(checkout, args[0]).startswith("approved ")
    if kind == "doc":
        return args[1] in (checkout / args[0]).read_text(encoding="utf-8")
    return False


def approved_seeds(checkout: Path) -> dict[str, dict[str, Any]]:
    """DEC-073 seed_v1 plus the owner's gitignored private store list, validated on the host."""
    if not dec_status(checkout, "DEC-073").startswith("approved "):
        raise RuntimeError("DEC-073 seed approval is not recorded in docs/DECISIONS.md")
    seeds = read_seed(checkout / "infra/seeds/seed_v1.yaml")
    if any(s["version"] != "seed_v1" or s["status"] != "approved" for s in seeds.values()):
        raise RuntimeError("infra/seeds/seed_v1.yaml approval metadata is not approved seed_v1")
    private = sorted((checkout / "infra/seeds").glob("private*"))
    if len(private) > 1:
        raise RuntimeError("More than one infra/seeds/private* file")
    if private:
        try:
            # Format: {"stores": [{"domain", "name", "enabled"}, ...]}, appended to seed_v1 stores.
            data = json.loads(comments_stripped(private[0]), object_pairs_hook=_unique_object)
            if set(data) != {"stores"}:
                raise ValueError
            stores = seeds["shopify_stores"]
            stores["entries"] = validate_seed_entries("stores", stores["entries"] + data["stores"])
        except OSError, ValueError, TypeError:
            raise RuntimeError("Private seed file is invalid; details withheld") from None
    return seeds


def source_op(
    checkout: Path, op: str, source: str | None, run: backup.Runner, emit: Callable[[str], None]
) -> None:
    """Seeds, enable or disable inside the collector worker container (Playbook §6 steps 3-4)."""

    def refuse(message: str) -> RuntimeError:
        emit(f"Refused: {message}")
        return RuntimeError(message)

    payload = None
    if op == "seeds":
        try:
            payload = json.dumps(approved_seeds(checkout))
        except RuntimeError as exc:
            raise refuse(str(exc)) from None
        except (OSError, ValueError) as exc:  # seed_v1 is public; private errors are generic
            raise refuse(f"seed_v1 invalid: {exc}") from None
    if op == "enable":
        assert source is not None
        closed = []
        for label, kind, args in GATES[source]:
            try:
                ok = passes(checkout, run, kind, args)
            except OSError, RuntimeError:  # failed or missing tests, missing files, a new hold
                ok = False
            reason = f" -- {args[0]}" if kind == "closed" else ""
            emit(f"gate {'open' if ok else 'closed'}: {source}: {label}{reason}")
            if not ok:
                closed.append(label)
        if closed:
            raise refuse(f"{len(closed)} step-4 gate(s) closed for {source}")
    rows = containers(checkout, run)
    if not any(row["Service"] == "postgres" and row["State"] == "running" for row in rows):
        raise refuse("collector Postgres is not running; run start first")
    command = [op, *filter(None, [source])]
    result = json.loads(
        run([*COMPOSE, *CONTAINER, *command], checkout, payload).rpartition("\n")[2]
    )
    if "refused" in result:
        raise refuse(f"{source}: {result['refused']}")
    emit(f"{' '.join(command)}: {json.dumps(result)}")
    emit("Check Data Health (first run, freshness, blocks) before the next source change")


def execute(
    checkout: Path,
    op: str,
    source: str | None = None,
    *,
    directory: Path = backup.DIRECTORY,
    run: backup.Runner = backup.command,
    open_snapshot: backup.SnapshotFactory = backup.snapshot,
) -> None:
    checkout = checkout.resolve()
    if (op in ("enable", "disable")) != (source in SOURCES):
        raise ValueError("enable and disable take one known collector source; other ops none")
    backup.preflight(checkout, run)
    if not (checkout / ".env.collector").is_file():
        raise RuntimeError("Owner must supply .env.collector")
    previous = checkout / ".git/pulso-collector-op.json"
    last_op = json.loads(previous.read_text("utf-8")) if previous.exists() else None

    def checked(args: list[str], cwd: Path, stdin: str | None) -> str:
        if (checkout / ".collector-hold").exists():
            raise RuntimeError("Collector hold file is present")
        return run(args, cwd, stdin)

    def compose(*args: str) -> str:
        return checked([*COMPOSE, *args], checkout, None)

    with backup.operation(checkout, f"{op}-{source}" if source else op, run) as emit:
        if op in ("seeds", "enable", "disable"):
            source_op(checkout, op, source, checked, emit)
            return
        rows = containers(checkout, checked)
        running = {row["Service"] for row in rows if row["State"] == "running"}
        if op == "status":
            revision = (
                backup.metadata(checkout, "pulso", checked, backup.REVISION)["alembic_version"]
                if "postgres" in running
                else None
            )
            emit(json.dumps({"containers": rows, "alembic_revision": revision, "last_op": last_op}))
            return
        if op == "start" and set(INFRA + CONSUMERS) <= running:
            emit("Stack already running; no changes")
            return
        if op == "update":
            checked(["git", "pull", "--ff-only"], checkout, None)
        emit("Building application images")
        compose("build", "worker", "migrate")
        compose("stop", *CONSUMERS)
        compose("up", "-d", "--wait", *INFRA)
        backup.create_dump(checkout, directory, emit, run=checked, open_snapshot=open_snapshot)
        emit("Applying migrations from the API image")
        compose("run", "--rm", "--no-deps", "-T", "migrate")
        compose("run", "--rm", "--no-deps", "-T", "worker", "python", "-m", "pulso_core.s3", "init")
        resume = (
            [service for service in CONSUMERS if service in running]
            if op == "migrate"
            else CONSUMERS
        )
        if resume:
            compose("up", "-d", "--wait", *resume)
        emit("Operation complete; check Data Health before enabling another source")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "op", choices=("start", "update", "migrate", "status", "seeds", "enable", "disable")
    )
    parser.add_argument("source", nargs="?", choices=SOURCES, help="enable/disable only")
    parser.add_argument("--checkout", type=Path, default=backup.CHECKOUT)
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if (args.op in ("enable", "disable")) != (args.source is not None):
        parser.error("enable and disable take exactly one source; other operations take none")
    checkout = args.checkout.resolve()
    try:
        if args.execute or args.op == "status":
            execute(checkout, args.op, args.source)
        else:
            backup.detach(
                checkout,
                [
                    sys.executable,
                    "-m",
                    "infra.scripts.collector",
                    args.op,
                    *filter(None, [args.source]),
                    "--checkout",
                    str(checkout),
                    "--execute",
                ],
            )
        return 0
    except Exception as exc:
        print(f"Collector refused or failed: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
