from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from celery.signals import beat_init, worker_process_init  # type: ignore[import-untyped]

from pulso_core.settings import Settings, get_settings
from pulso_workers import beat


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(beat, "__file__", str(tmp_path / "installed" / "beat.py"))
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
@pytest.mark.parametrize("entrypoint", ["main", "signal"])
def test_beat_refuses_disabled_scheduler(
    monkeypatch: pytest.MonkeyPatch, flag: str | None, entrypoint: str
) -> None:
    from pulso_workers.celery_app import app

    if flag is not None:
        monkeypatch.setenv("PULSO_SCHEDULER", flag)
    with pytest.raises(SystemExit, match="PULSO_SCHEDULER=on"):
        if entrypoint == "main":
            beat.main()
        else:
            beat_init.send(sender=app)


@pytest.mark.parametrize("origin", ["cwd", "package"])
@pytest.mark.parametrize("entrypoint", ["main", "signal"])
def test_beat_refuses_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, origin: str, entrypoint: str
) -> None:
    from pulso_workers.celery_app import app

    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    worktree = tmp_path / "worktree"
    nested = worktree / "apps"
    nested.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: /unused/worktrees/test", encoding="utf-8")
    if origin == "cwd":
        monkeypatch.chdir(nested)
    else:
        monkeypatch.setattr(beat, "__file__", str(nested / "beat.py"))
    with pytest.raises(SystemExit, match="linked git worktree"):
        if entrypoint == "main":
            beat.main()
        else:
            beat_init.send(sender=app)


def test_enabled_beat_calls_celery_without_running_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from pulso_workers.beat import main
    from pulso_workers.celery_app import app

    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    (tmp_path / ".git").mkdir()
    start = Mock()
    monkeypatch.setattr(app, "start", start)
    main()
    start.assert_called_once_with(["beat", "--loglevel=INFO"])


def test_process_signal_creates_engine(monkeypatch: pytest.MonkeyPatch) -> None:
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
