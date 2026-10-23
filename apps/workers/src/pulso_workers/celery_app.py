"""Celery entry point; importing this module never opens database connections."""

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import beat_init, worker_process_init  # type: ignore[import-untyped]
from sqlalchemy import Engine

from pulso_core.db import get_engine
from pulso_core.logging import configure_logging
from pulso_core.settings import get_settings
from pulso_workers.beat import init_scheduler
from pulso_workers.schedules import BEAT_SCHEDULE

app = Celery("pulso")
engine: Engine | None = None


def configuration() -> dict[str, object]:
    return {
        "broker_url": get_settings().redis_url.get_secret_value(),
        "timezone": "UTC",
        "enable_utc": True,
        "task_ignore_result": True,
        "task_default_queue": "default",
        "worker_prefetch_multiplier": 1,
        "worker_concurrency": 1,
        "broker_connection_retry_on_startup": True,
        "beat_scheduler": "pulso_workers.beat:LockedScheduler",
        "beat_schedule": BEAT_SCHEDULE,
        "beat_max_loop_interval": 5,
        "imports": ("pulso_workers.tasks", "pulso_workers.ops", "pulso_workers.registration"),
        "task_routes": {
            "collect.*": {"queue": "collect"},
            "ops.*": {"queue": "ops"},
            "audit.*": {"queue": "ops"},
        },
        "task_annotations": {
            "collect.run": {
                "soft_time_limit": get_settings().collect_soft_time_limit_seconds,
                "time_limit": get_settings().collect_hard_time_limit_seconds,
            }
        },
    }


app.add_defaults(configuration)


def init_process(**kwargs: object) -> None:
    global engine
    configure_logging(get_settings().log_level)
    if engine is not None:
        engine.dispose(close=False)  # Never close sockets inherited from another process.
    engine = get_engine()


worker_process_init.connect(init_process, weak=False)
beat_init.connect(init_scheduler, weak=False)


def ping() -> str:
    return "pong"


app.task(name="pulso.ping")(ping)
