from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest

from pulso_core.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_ping_in_eager_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from pulso_workers.celery_app import app

    assert app.conf.broker_url == "redis://localhost:6379/15"
    monkeypatch.setitem(app.conf, "task_always_eager", True)
    monkeypatch.setitem(app.conf, "task_eager_propagates", True)
    assert app.tasks["pulso.ping"].delay().get() == "pong"
    assert app.conf.beat_schedule == {}


@pytest.mark.parametrize("flag", [None, "off", "false", "0"])
def test_beat_refuses_disabled_scheduler(monkeypatch: pytest.MonkeyPatch, flag: str | None) -> None:
    from pulso_workers.beat import main

    if flag is not None:
        monkeypatch.setenv("PULSO_SCHEDULER", flag)
    with pytest.raises(SystemExit, match="PULSO_SCHEDULER=on"):
        main()


def test_beat_refuses_worktree(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from pulso_workers.beat import main

    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    (tmp_path / ".git").write_text("gitdir: /unused/worktrees/test", encoding="utf-8")
    nested = tmp_path / "apps"
    nested.mkdir()
    monkeypatch.chdir(nested)
    with pytest.raises(SystemExit, match="linked git worktree"):
        main()


def test_enabled_beat_calls_celery_without_running_it(monkeypatch: pytest.MonkeyPatch) -> None:
    from pulso_workers.beat import main
    from pulso_workers.celery_app import app

    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    start = Mock()
    monkeypatch.setattr(app, "start", start)
    main()
    start.assert_called_once_with(["beat", "--loglevel=INFO"])


def test_process_signal_creates_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    from celery.signals import worker_process_init  # type: ignore[import-untyped]

    from pulso_workers import celery_app

    assert celery_app.engine is None
    factory = Mock()
    monkeypatch.setattr(celery_app, "create_engine", factory)
    monkeypatch.setattr(celery_app, "engine", None)
    created_engine = factory.return_value
    worker_process_init.send(sender=None)
    factory.assert_called_once_with(
        "postgresql+psycopg://test:test@localhost/pulso_test", pool_size=3, max_overflow=0
    )
    assert celery_app.engine == created_engine
    worker_process_init.send(sender=None)
    created_engine.dispose.assert_called_once_with(close=False)
    assert factory.call_count == 2
