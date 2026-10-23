"""Collector-host-only Beat, fenced by a dedicated PostgreSQL session."""

import logging
from typing import Any

from celery.beat import PersistentScheduler  # type: ignore[import-untyped]

from pulso_core.logging import configure_logging
from pulso_core.settings import get_settings
from pulso_core.worktree import is_linked_worktree
from pulso_workers.locks import AdvisoryLock

logger = logging.getLogger("pulso.scheduler")


def guard_scheduler(**kwargs: object) -> None:
    if not get_settings().pulso_scheduler:
        logger.error("Beat requires PULSO_SCHEDULER=on on the collector host.")
        raise SystemExit("Beat requires PULSO_SCHEDULER=on on the collector host.")
    if is_linked_worktree(__file__):
        raise SystemExit("Beat is forbidden inside a linked git worktree.")


class LockedScheduler(PersistentScheduler):  # type: ignore[misc]
    lock: AdvisoryLock | None = None

    @property
    def producer(self) -> None:
        # Beat's eager broker connection logs exception text before our publish boundary.
        return None

    def setup_schedule(self) -> None:
        guard_scheduler()
        super().setup_schedule()

    def tick(self, **kwargs: Any) -> float:
        try:
            held = self.lock is not None and self.lock.held()
        except Exception:
            held = False
        if not held:
            logger.error("scheduler_lock_lost")
            raise SystemExit(1)
        return float(super().tick(**kwargs))

    def apply_entry(self, entry: Any, producer: Any = None) -> None:
        from pulso_workers.ops import publish_ops
        from pulso_workers.tasks import enqueue_scheduled

        if entry.task in {"ops.heartbeat", "audit.schedule"}:
            publish_ops(entry.task)
            return
        try:
            enqueue_scheduled(*entry.args)
        except Exception as exc:
            # Beat survives a DB outage; the gap audit and SCH-4 catch-up recover the slot.
            logger.error("run_enqueue_failed", extra={"error_type": type(exc).__name__})

    def close(self) -> None:
        try:
            super().close()
        finally:
            if self.lock is not None:
                self.lock.close()


def init_scheduler(sender: Any, **kwargs: object) -> None:
    configure_logging(get_settings().log_level)
    guard_scheduler()
    if not isinstance(sender.scheduler, LockedScheduler):
        raise SystemExit("Beat requires LockedScheduler.")
    lock = AdvisoryLock(0)
    try:
        if not lock.acquire():
            raise RuntimeError("scheduler_lock_held")
    except Exception:
        lock.close()
        logger.error("scheduler_lock_unavailable")
        raise SystemExit(1) from None
    sender.scheduler.lock = lock
    from pulso_workers.ops import publish_ops

    publish_ops("audit.schedule")


def main() -> None:
    guard_scheduler()

    from pulso_workers.celery_app import app

    app.start(["beat", "--loglevel=INFO"])


if __name__ == "__main__":
    main()
