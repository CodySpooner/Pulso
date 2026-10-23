"""Publish run ids without importing worker or ML code into the API image."""

from collections.abc import Callable

from celery import Celery  # type: ignore[import-untyped]

from pulso_core.settings import get_settings

publisher = Celery("pulso-api")
publisher.add_defaults(lambda: {"broker_url": get_settings().redis_url.get_secret_value()})


def publish_run(run_id: int) -> None:
    publisher.send_task("collect.run", args=[run_id], queue="collect", retry=False)


def get_publisher() -> Callable[[int], object]:
    return publish_run
