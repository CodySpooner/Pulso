from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from celery.beat import PersistentScheduler  # type: ignore[import-untyped]
from celery.schedules import crontab  # type: ignore[import-untyped]
from celery.signals import beat_init, worker_process_init  # type: ignore[import-untyped]
from sqlalchemy.engine import Engine

from pulso_core import db
from pulso_workers import beat


def test_ping_in_eager_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from pulso_workers.celery_app import app

    assert app.conf.broker_url == "redis://localhost:6379/15"
    monkeypatch.setitem(app.conf, "task_always_eager", True)
    monkeypatch.setitem(app.conf, "task_eager_propagates", True)
    assert app.tasks["pulso.ping"].delay().get() == "pong"
    assert all(isinstance(entry["schedule"], crontab) for entry in app.conf.beat_schedule.values())
    assert app.conf.worker_concurrency == 1
    assert app.conf.task_routes["ops.*"]["queue"] == "ops"
    assert app.conf.task_annotations["collect.run"] == {"soft_time_limit": 3600, "time_limit": 4500}


@pytest.mark.parametrize("flag", [None, "off", "false", "0"])
@pytest.mark.parametrize("entrypoint", ["main", "signal"])
def test_beat_refuses_disabled_scheduler(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
    flag: str | None,
    entrypoint: str,
) -> None:
    from pulso_workers.celery_app import app

    if flag is not None:
        monkeypatch.setenv("PULSO_SCHEDULER", flag)
    with pytest.raises(SystemExit, match="PULSO_SCHEDULER=on"):
        if entrypoint == "main":
            beat.main()
        else:
            beat_init.send(sender=app)
    assert "Beat requires PULSO_SCHEDULER=on" in caplog.text + capsys.readouterr().err


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
    monkeypatch.setattr(celery_app, "engine", None)
    db._process_engine.cache_clear()
    try:
        with patch.object(db, "create_engine", side_effect=lambda *a, **k: Mock()) as factory:
            worker_process_init.send(sender=None)
            created_engine = celery_app.engine
            assert created_engine is db.get_engine()
            factory.assert_called_once_with(
                "postgresql+psycopg://test:test@localhost/pulso_test",
                pool_pre_ping=True,
                hide_parameters=True,
                connect_args={"connect_timeout": 3, "options": "-c timezone=UTC"},
            )
            with patch("pulso_core.db.os.getpid", return_value=-1):
                worker_process_init.send(sender=None)
                assert celery_app.engine is db.get_engine()
                assert celery_app.engine is not created_engine
            assert isinstance(created_engine, Mock)
            created_engine.dispose.assert_called_once_with(close=False)
            assert factory.call_count == 2
    finally:
        db._process_engine.cache_clear()


@pytest.mark.parametrize("failure", [False, ConnectionError("fixture-lock-secret")])
def test_tick_stops_before_scheduling_when_lock_drops(failure: object) -> None:
    from pulso_workers.celery_app import app

    scheduler = beat.LockedScheduler(app=app, lazy=True)
    scheduler.lock = Mock()
    scheduler.lock.held.side_effect = [failure]
    with patch.object(PersistentScheduler, "tick") as tick:
        with pytest.raises(SystemExit):
            scheduler.tick()
        tick.assert_not_called()
    assert scheduler.producer is None


@pytest.mark.db
def test_second_beat_exits_and_dropped_session_stops_ticks(
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pulso_workers import locks
    from pulso_workers.celery_app import app

    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    monkeypatch.setattr(locks, "get_engine", lambda: db_engine)
    key = 65536 + uuid4().int % (2**31 - 65536)
    monkeypatch.setattr(beat, "AdvisoryLock", lambda _: locks.AdvisoryLock(key))
    first, second = (beat.LockedScheduler(app=app, lazy=True) for _ in range(2))
    beat_init.send(sender=Mock(scheduler=first))
    assert first.lock is not None and first.lock.held()
    try:
        with pytest.raises(SystemExit) as error:
            beat_init.send(sender=Mock(scheduler=second))
        assert error.value.code == 1
        first.lock.close()
        with pytest.raises(SystemExit):
            first.tick()
        beat_init.send(sender=Mock(scheduler=second))
        assert second.lock is not None and second.lock.held()
        second.lock.close()
    finally:
        first.lock.close()


def test_api_override_uses_real_collect_publisher(monkeypatch: pytest.MonkeyPatch) -> None:
    from pulso_api.main import create_app
    from pulso_api.publisher import publisher
    from pulso_api.routers.admin import get_publisher

    send = Mock()
    monkeypatch.setattr(publisher, "send_task", send)
    create_app().dependency_overrides[get_publisher]()(7)
    send.assert_called_once_with("collect.run", args=[7], queue="collect", retry=False)
