"""Run from the repo root: uv run --frozen python -m infra.scripts.collector OP."""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# P1-14 is also a direct script; both entry points use its existing import path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup  # noqa: E402

COMPOSE = [*backup.COMPOSE, "--profile", "collector"]
INFRA = ["postgres", "redis", "s3"]
CONSUMERS = ["beat", "worker", "worker-ops"]


def containers(checkout: Path, run: backup.Runner) -> list[dict[str, Any]]:
    output = run([*COMPOSE, "ps", "--all", "--format", "json"], checkout, None)
    rows = (
        json.loads(output)
        if output.startswith("[")
        else [json.loads(line) for line in output.splitlines()]
    )
    return [{key: row.get(key, "") for key in ("Service", "State", "Health")} for row in rows]


def execute(
    checkout: Path,
    op: str,
    *,
    directory: Path = backup.DIRECTORY,
    run: backup.Runner = backup.command,
    open_snapshot: backup.SnapshotFactory = backup.snapshot,
) -> None:
    checkout = checkout.resolve()
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

    with backup.operation(checkout, op, run) as emit:
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
    parser.add_argument("op", choices=("start", "update", "migrate", "status"))
    parser.add_argument("--checkout", type=Path, default=backup.CHECKOUT)
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    checkout = args.checkout.resolve()
    try:
        if args.execute or args.op == "status":
            execute(checkout, args.op)
        else:
            backup.detach(
                checkout,
                [
                    sys.executable,
                    "-m",
                    "infra.scripts.collector",
                    args.op,
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
