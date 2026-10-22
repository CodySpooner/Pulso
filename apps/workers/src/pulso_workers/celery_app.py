"""Celery entry point; importing this module never opens database connections."""

from celery import Celery  # type: ignore[import-untyped]
from celery.signals import beat_init, worker_process_init  # type: ignore[import-untyped]
from sqlalchemy import Engine, create_engine

from pulso_core.settings import get_settings
from pulso_workers.beat import guard_scheduler

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
        "broker_connection_retry_on_startup": True,
        "beat_schedule": {},
    }


app.add_defaults(configuration)


def init_process(**kwargs: object) -> None:
    global engine
    if engine is not None:
        engine.dispose(close=False)  # Never close sockets inherited from another process.
    engine = create_engine(
        get_settings().database_url.get_secret_value(), pool_size=3, max_overflow=0
    )


worker_process_init.connect(init_process, weak=False)
beat_init.connect(guard_scheduler, weak=False)


def ping() -> str:
    return "pong"


app.task(name="pulso.ping")(ping)
