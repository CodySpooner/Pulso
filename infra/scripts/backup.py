"""Collector database backup; run only on the owner-managed checkout."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, NonNegativeInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.db import make_engine
from pulso_core.models import CollectorRun, Source

CHECKOUT = Path("C:/dev/pulso")
DIRECTORY = Path("C:/Users/Xody2/OneDrive/Pulso Backups/db")
STAMP = "%Y%m%dT%H%M%S%fZ"
COMPOSE = [
    "docker",
    "compose",
    "-p",
    "pulso-collector",
    "--env-file",
    ".env",
    "--env-file",
    ".env.collector",
    "-f",
    "infra/docker-compose.yml",
]
Runner = Callable[[list[str], Path, str | None], str]
SnapshotFactory = Callable[[Path], AbstractContextManager[tuple[str, dict[str, object]]]]

# Count every public table, including future snapshot/forecast tables, in the same transaction.
REVISION = r"""
SELECT to_regclass('public.alembic_version') IS NOT NULL AS has_revision \gset
\if :has_revision
SELECT json_build_object('server_version', current_setting('server_version'),
  'alembic_version', (SELECT coalesce(json_agg(version_num ORDER BY version_num), '[]'::json)
                    FROM alembic_version));
\else
SELECT json_build_object('server_version', current_setting('server_version'),
  'alembic_version', '[]'::json);
\endif
"""
METADATA = (
    REVISION
    + r"""
SELECT format('SELECT json_build_object(''table'', %L, ''count'', count(*)) FROM %I.%I',
  table_name, table_schema, table_name)
FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name
\gexec
"""
)
PSQL = ["psql", "-XqAt", "--set", "ON_ERROR_STOP=1", "-U", "pulso", "-d"]


class Manifest(BaseModel):
    coverage: Literal["database only"] = "database only"
    raw_object_coverage: Literal["none"] = "none"
    sha256: str
    captured_at: datetime
    server_version: str
    alembic_version: list[str]
    row_counts: dict[str, NonNegativeInt]


def command(args: list[str], checkout: Path, stdin: str | None = None) -> str:
    result = subprocess.run(
        args,
        cwd=checkout,
        input=stdin,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )
    if result.returncode:
        # Subprocess diagnostics can include credentials or restored row data.
        raise RuntimeError(f"{args[0]} failed (exit {result.returncode}); output withheld")
    return result.stdout.strip()


def preflight(checkout: Path, run: Runner = command) -> None:
    if not (checkout / ".git").is_dir():
        raise RuntimeError("A primary checkout is required; linked worktrees are refused")
    if (checkout / ".collector-hold").exists():
        raise RuntimeError("Collector hold file is present")
    if (checkout / ".git/pulso-collector-op.lock").exists():
        raise RuntimeError("Collector operation lock is held")
    checks = [
        (["status", "--porcelain", "--untracked-files=no"], "", "Checkout is dirty"),
        (["branch", "--show-current"], "main", "Checkout must be on main"),
        (["rev-list", "--count", "origin/main..HEAD"], "0", "Checkout is ahead of origin/main"),
    ]
    for args, expected, message in checks:
        if run(["git", *args], checkout, None) != expected:
            raise RuntimeError(message)


def write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


@contextmanager
def operation(checkout: Path, op: str, run: Runner = command) -> Iterator[Callable[[str], None]]:
    preflight(checkout, run)
    lock = checkout / ".git/pulso-collector-op.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError("Collector operation lock is held") from None
    log = checkout / f".git/pulso-{op}-{datetime.now(UTC).strftime(STAMP)}.log"
    status: dict[str, object] = {
        "op": op,
        "started": datetime.now(UTC).isoformat(),
        "finished": None,
        "exit": None,
        "log": str(log),
    }

    def emit(message: str) -> None:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"at": datetime.now(UTC).isoformat(), "op": op, "message": message})
                + "\n"
            )
        print(message, flush=True)

    try:
        write_json(checkout / ".git/pulso-collector-op.json", status)
        emit("Operation started")
        yield emit
        status["exit"] = 0
    except BaseException as exc:
        status["exit"] = 1
        emit(f"Operation failed: {type(exc).__name__}")
        raise
    finally:
        status["finished"] = datetime.now(UTC).isoformat()
        try:
            write_json(checkout / ".git/pulso-collector-op.json", status)
        finally:
            lock.rmdir()


def postgres(checkout: Path, args: list[str], run: Runner, stdin: str | None = None) -> str:
    return run([*COMPOSE, "exec", "-T", "postgres", *args], checkout, stdin)


def metadata(checkout: Path, db: str, run: Runner, sql: str = METADATA) -> dict[str, object]:
    output = postgres(checkout, [*PSQL, db], run, sql)
    return parse_metadata(output)


def parse_metadata(output: str) -> dict[str, object]:
    rows = [json.loads(line) for line in output.splitlines()]
    return {**rows[0], "row_counts": {row["table"]: row["count"] for row in rows[1:]}}


@contextmanager
def snapshot(checkout: Path) -> Iterator[tuple[str, dict[str, object]]]:
    # Keep the exporting transaction alive until the separate pg_dump process finishes.
    with subprocess.Popen(
        [*COMPOSE, "exec", "-T", "postgres", *PSQL, "pulso"],
        cwd=checkout,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
    ) as process:
        assert process.stdin is not None and process.stdout is not None
        try:
            process.stdin.write(
                "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;\n"
                "SELECT pg_export_snapshot();\n" + METADATA + "\n\\echo READY\n"
            )
            process.stdin.flush()
            token = process.stdout.readline().strip()
            if not re.fullmatch(r"[0-9A-Fa-f]+-[0-9A-Fa-f]+-[0-9]+", token):
                raise RuntimeError("Could not export database snapshot")
            lines = []
            while (line := process.stdout.readline()) and line.strip() != "READY":
                lines.append(line)
            if not line:
                raise RuntimeError("Could not read snapshot counts")
            yield token, parse_metadata("".join(lines))
        finally:
            try:
                process.communicate("ROLLBACK;\n", timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise RuntimeError("Snapshot session did not finish") from None
        if process.returncode:
            raise RuntimeError("Snapshot session failed; output withheld")


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump_time(path: Path) -> datetime | None:
    match = re.fullmatch(r"pulso-(\d{8}T\d{6}\d{6}Z)\.dump", path.name)
    try:
        return datetime.strptime(match[1], STAMP).replace(tzinfo=UTC) if match else None
    except ValueError:
        return None


def expired_dumps(paths: Sequence[Path]) -> list[Path]:
    """Keep the latest per UTC date (14), latest Sundays (8), and newest three files."""
    dated = sorted(((stamp, path) for path in paths if (stamp := dump_time(path))), reverse=True)
    keep = {path for _, path in dated[:3]}
    daily: set[date] = set()
    weekly: set[date] = set()
    for stamp, path in dated:
        day = stamp.date()
        if day not in daily and len(daily) < 14:
            daily.add(day)
            keep.add(path)
        if stamp.weekday() == 6 and day not in weekly and len(weekly) < 8:
            weekly.add(day)
            keep.add(path)
    return [path for _, path in dated if path not in keep]


def record_run(database_url: str, started: datetime, success: bool) -> None:
    engine = make_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            source = session.scalar(select(Source.id).where(Source.key == "backup"))
            if source is None:
                raise RuntimeError("Backup pseudo-source is missing")
            session.add(
                CollectorRun(
                    source_id=source,
                    trigger="manual",
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    status="success" if success else "failed",
                    complete=success,
                    params={"coverage": "database only", "raw_object_coverage": "none"},
                )
            )
    finally:
        engine.dispose()


def backup(
    checkout: Path,
    directory: Path,
    *,
    delete_expired: bool = False,
    database_url: str | None = None,
    run: Runner = command,
    open_snapshot: SnapshotFactory = snapshot,
) -> Path:
    with operation(checkout, "backup", run) as emit:
        return create_dump(
            checkout,
            directory,
            emit,
            delete_expired=delete_expired,
            database_url=database_url,
            run=run,
            open_snapshot=open_snapshot,
        )


def create_dump(
    checkout: Path,
    directory: Path,
    emit: Callable[[str], None],
    *,
    delete_expired: bool = False,
    database_url: str | None = None,
    run: Runner = command,
    open_snapshot: SnapshotFactory = snapshot,
) -> Path:
    """Write a verified backup while the caller holds the collector operation lock."""
    started = datetime.now(UTC)
    success = False
    temporary: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        dump = directory / f"pulso-{started.strftime(STAMP)}.dump"
        temporary = dump.with_suffix(".dump.partial")
        with open_snapshot(checkout) as (token, details):
            postgres(
                checkout,
                [
                    "pg_dump",
                    "-U",
                    "pulso",
                    "-d",
                    "pulso",
                    "-Fc",
                    "-f",
                    "/tmp/pulso.dump",
                    "--snapshot",
                    token,
                ],
                run,
            )
        postgres(checkout, ["pg_restore", "--list", "/tmp/pulso.dump"], run)
        run([*COMPOSE, "cp", "postgres:/tmp/pulso.dump", str(temporary)], checkout, None)
        manifest = Manifest.model_validate(
            {**details, "captured_at": started, "sha256": checksum(temporary)}
        )
        write_json(dump.with_suffix(".manifest.json"), manifest.model_dump(mode="json"))
        temporary.rename(dump)
        success = True
        emit(f"Saved {dump.name}: database only; raw-object coverage none")
        candidates = [
            p for p in directory.glob("pulso-*.dump") if p.is_file() and not p.is_symlink()
        ]
        for path in expired_dumps(candidates):
            emit(f"Retention {'delete' if delete_expired else 'would expire'}: {path.name}")
            if delete_expired:
                path.unlink()
        return dump
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if database_url:
            try:
                record_run(database_url, started, success)
            except Exception as exc:
                emit(f"Backup run recording failed: {type(exc).__name__}; dump retained")


def arguments(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--checkout", type=Path, default=CHECKOUT)
    parser.add_argument("--directory", type=Path, default=DIRECTORY)
    parser.add_argument("--detach", action="store_true")
    return parser


def detach(checkout: Path, child_args: list[str] | None = None) -> None:
    preflight(checkout)
    flags = 0
    # mypy only narrows sys.platform in if-statements; these flags exist only on Windows.
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        child_args
        or [
            sys.executable,
            str(Path(sys.argv[0]).resolve()),
            *(arg for arg in sys.argv[1:] if arg != "--detach"),
        ],
        cwd=checkout,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        start_new_session=os.name != "nt",
    )
    print("Operation launched; inspect .git/pulso-collector-op.json for completion")


def main() -> int:
    parser = arguments(__doc__ or "Backup")
    parser.add_argument("--delete-expired", action="store_true")
    args = parser.parse_args()
    try:
        if args.detach:
            detach(args.checkout)
        else:
            backup(
                args.checkout,
                args.directory,
                delete_expired=args.delete_expired,
                database_url=os.environ.get("DATABASE_URL"),
            )
        return 0
    except Exception as exc:
        print(
            f"Backup refused or failed: {type(exc).__name__}: {exc}"
            if isinstance(exc, RuntimeError)
            else f"Backup failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
