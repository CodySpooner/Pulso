"""Run from the repo root: uv run python -m infra.scripts.seeds [--apply]."""

import argparse
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from pulso_core.db import get_session

from . import DEFAULT_SEED, load_seeds, read_seed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Preview seed config changes; never enable sources"
    )
    parser.add_argument("--seed-file", type=Path, default=DEFAULT_SEED)
    parser.add_argument(
        "--apply", action="store_true", help="commit changes to the configured database"
    )
    args = parser.parse_args(argv)
    try:
        seeds = read_seed(args.seed_file)
        with get_session() as session, session.begin():
            changed = load_seeds(session, seeds, apply=args.apply)
    except ValidationError:
        parser.error("Invalid environment settings; check the worktree configuration")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    except SQLAlchemyError:
        parser.error("Database operation failed; check the worktree database and migrations")
    print(f"{'Applied' if args.apply else 'Dry run (no writes)'}: {changed} source(s) changed")


if __name__ == "__main__":
    main()
