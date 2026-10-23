"""Restore verification into a newly created scratch database only."""

import os
import re
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from backup import (
    COMPOSE,
    Manifest,
    Runner,
    arguments,
    checksum,
    command,
    detach,
    dump_time,
    metadata,
    operation,
    postgres,
)


def validate_target(db: str, database_url: str | None) -> None:
    if not re.fullmatch(r"pulso_restore_check[a-z0-9_]*", db) or len(db) > 63:
        raise RuntimeError(
            "Target must start with pulso_restore_check; use lowercase letters/digits/_"
        )
    if database_url and db == make_url(database_url).database:
        raise RuntimeError("Target is the collector database")


def restore(
    checkout: Path,
    directory: Path,
    db: str,
    *,
    file: Path | None = None,
    database_url: str | None = None,
    run: Runner = command,
) -> None:
    validate_target(db, database_url)
    with operation(checkout, "restore", run) as emit:
        if file is None:
            dumps = sorted(
                p
                for p in directory.glob("pulso-*.dump")
                if dump_time(p) and p.is_file() and not p.is_symlink()
            )
            if not dumps:
                raise RuntimeError("No completed dump found")
            file = dumps[-1]
        manifest = Manifest.model_validate_json(
            file.with_suffix(".manifest.json").read_text("utf-8")
        )
        if checksum(file) != manifest.sha256:
            raise RuntimeError("Dump checksum does not match manifest")
        emit("Database only; raw-object checks (BAK-2 R-11) are a later task")
        run([*COMPOSE, "cp", str(file), "postgres:/tmp/pulso.restore.dump"], checkout, None)
        postgres(checkout, ["pg_restore", "--list", "/tmp/pulso.restore.dump"], run)
        postgres(checkout, ["createdb", "-U", "pulso", "-T", "template0", db], run)
        try:
            postgres(
                checkout,
                [
                    "pg_restore",
                    "-U",
                    "pulso",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    db,
                    "/tmp/pulso.restore.dump",
                ],
                run,
            )
            actual = metadata(checkout, db, run)
            if actual["row_counts"] != manifest.row_counts:
                raise RuntimeError("Restored row counts do not match manifest")
            if actual["alembic_version"] != manifest.alembic_version:
                raise RuntimeError("Restored migration revision does not match manifest")
            emit("Restore row counts and migration revision match manifest")
        finally:
            postgres(checkout, ["dropdb", "-U", "pulso", db], run)
            emit(f"Removed scratch database {db}")


def main() -> int:
    parser = arguments(__doc__ or "Restore")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--latest", action="store_true")
    source.add_argument("--file", type=Path)
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    try:
        validate_target(args.db, os.environ.get("DATABASE_URL"))
        if args.detach:
            detach(args.checkout)
        else:
            restore(
                args.checkout,
                args.directory,
                args.db,
                file=args.file,
                database_url=os.environ.get("DATABASE_URL"),
            )
        return 0
    except Exception as exc:
        print(
            f"Restore refused or failed: {type(exc).__name__}: {exc}"
            if isinstance(exc, RuntimeError)
            else f"Restore failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
