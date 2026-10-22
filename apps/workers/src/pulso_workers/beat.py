"""Guarded Beat entry point; schedules and the DEC-002 lock arrive in Phase 1."""

from pathlib import Path

from pulso_core.settings import get_settings


def main() -> None:
    if not get_settings().pulso_scheduler:
        raise SystemExit("Beat requires PULSO_SCHEDULER=on on the collector host.")
    for path in (Path.cwd(), *Path.cwd().parents):
        if (path / ".git").is_file():
            raise SystemExit("Beat is forbidden inside a linked git worktree.")

    # TODO(DEC-002, Phase 1): hold/check a Postgres advisory lock before enabling schedules.
    from pulso_workers.celery_app import app

    app.start(["beat", "--loglevel=INFO"])


if __name__ == "__main__":
    main()
