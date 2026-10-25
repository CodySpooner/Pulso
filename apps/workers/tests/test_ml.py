import subprocess
import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, Mock, call

import pytest

from pulso_ml import embeddings
from pulso_ml.features import daily
from pulso_ml.matching import matcher
from pulso_sources.fx_frankfurter import rate_as_of
from pulso_sources.storage import read_capture
from pulso_workers import ml
from pulso_workers.celery_app import app


def test_matcher_task_runs_on_the_ml_queue() -> None:
    assert "ml.match" in app.tasks
    assert app.amqp.router.route({}, "ml.match")["queue"].name == "ml"
    assert all(entry["task"] != "ml.match" for entry in app.conf.beat_schedule.values())


@pytest.mark.parametrize("flag", [None, "off"])
def test_flag_off_logs_and_never_opens_the_database(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, flag: str | None
) -> None:
    if flag is not None:
        monkeypatch.setenv("MATCHER_ENABLED", flag)
    caplog.set_level("INFO", logger="pulso.ml")
    get_session = Mock(side_effect=AssertionError("database touched"))
    monkeypatch.setattr(ml, "get_session", get_session)
    app.tasks["ml.match"].apply(throw=True)
    get_session.assert_not_called()
    assert "matcher_disabled" in caplog.text


def test_flag_on_matches_with_stored_fx_and_logs_counts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("MATCHER_ENABLED", "on")
    caplog.set_level("INFO", logger="pulso.ml")
    session = MagicMock()
    monkeypatch.setattr(ml, "get_session", Mock(return_value=session))
    match = Mock(return_value=matcher.Counts(5, 1, 2, 2, 3, 4, 6))
    monkeypatch.setattr(matcher, "match", match)
    app.tasks["ml.match"].apply(throw=True)
    match.assert_called_once_with(session.__enter__.return_value, rate_as_of)
    assert (
        "scored=5 linked=1 queued=2 discarded=2 skipped_no_embedding=3 gtin_linked=4 gtin_queued=6"
        in caplog.text
    )


def test_importing_the_ml_jobs_never_imports_torch_or_open_clip() -> None:
    code = (
        "import sys, pulso_workers.ml, pulso_ml.embeddings;"
        " print(sorted({'torch', 'open_clip', 'huggingface_hub'} & sys.modules.keys()))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_embed_task_runs_on_the_ml_queue_without_a_schedule() -> None:
    assert "ml.embed" in app.tasks
    assert app.amqp.router.route({}, "ml.embed")["queue"].name == "ml"
    assert all(entry["task"] != "ml.embed" for entry in app.conf.beat_schedule.values())


@pytest.mark.parametrize("flag", [None, "off"])
def test_embed_flag_off_never_loads_the_model_or_opens_the_database(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, flag: str | None
) -> None:
    if flag is not None:
        monkeypatch.setenv("EMBEDDINGS_ENABLED", flag)
    caplog.set_level("INFO", logger="pulso.ml")
    get_session = Mock(side_effect=AssertionError("database touched"))
    monkeypatch.setattr(ml, "get_session", get_session)
    openclip = Mock(side_effect=AssertionError("model loaded"))
    monkeypatch.setattr(embeddings, "openclip", openclip)
    app.tasks["ml.embed"].apply(throw=True)
    get_session.assert_not_called()
    openclip.assert_not_called()
    assert "embeddings_disabled" in caplog.text


def test_embed_flag_on_reads_stored_captures_and_logs_counts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("EMBEDDINGS_ENABLED", "on")
    caplog.set_level("INFO", logger="pulso.ml")
    session = MagicMock()
    monkeypatch.setattr(ml, "get_session", Mock(return_value=session))
    encoder = object()
    monkeypatch.setattr(embeddings, "openclip", Mock(return_value=encoder))
    embed = Mock(return_value=embeddings.Counts(4, 7, 2, 1))
    monkeypatch.setattr(embeddings, "embed", embed)
    app.tasks["ml.embed"].apply(throw=True)
    embed.assert_called_once_with(session.__enter__.return_value, encoder, read_capture)
    assert (
        f"embeddings_done model={embeddings.MODEL_VERSION}"
        " images=4 titles=7 image_missing=2 image_unreadable=1" in caplog.text
    )


def test_features_task_runs_on_the_ml_queue_without_a_schedule() -> None:
    assert "ml.features" in app.tasks
    assert app.amqp.router.route({}, "ml.features")["queue"].name == "ml"
    assert all(entry["task"] != "ml.features" for entry in app.conf.beat_schedule.values())


@pytest.mark.parametrize("flag", [None, "off"])
def test_features_flag_off_logs_and_never_opens_the_database(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, flag: str | None
) -> None:
    if flag is not None:
        monkeypatch.setenv("FEATURES_ENABLED", flag)
    caplog.set_level("INFO", logger="pulso.ml")
    get_session = Mock(side_effect=AssertionError("database touched"))
    monkeypatch.setattr(ml, "get_session", get_session)
    app.tasks["ml.features"].apply(throw=True)
    get_session.assert_not_called()
    assert "features_disabled" in caplog.text


NOW = datetime(2026, 10, 25, 0, 30, tzinfo=UTC)  # just past midnight: local dates often differ


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Mock:
    clock = Mock(now=Mock(side_effect=lambda tz: NOW.astimezone(tz)))
    monkeypatch.setattr(ml, "datetime", clock)
    return clock


def run_features(monkeypatch: pytest.MonkeyPatch, **kwargs: str) -> tuple[Mock, MagicMock]:
    """Runs ml.features with the flag on; returns the run/commit calls in order, and the session."""
    monkeypatch.setenv("FEATURES_ENABLED", "on")
    session = MagicMock()
    monkeypatch.setattr(ml, "get_session", Mock(return_value=session))
    calls = Mock()
    calls.run.side_effect = lambda _, day: day.day  # rows written: the day of the month
    monkeypatch.setattr(daily, "run", calls.run)
    calls.attach_mock(session.__enter__.return_value.commit, "commit")
    app.tasks["ml.features"].apply(kwargs=kwargs, throw=True)
    return calls, session.__enter__.return_value


def test_features_default_to_yesterday_in_utc(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, clock: Mock
) -> None:
    caplog.set_level("INFO", logger="pulso.ml")
    calls, session = run_features(monkeypatch)
    clock.now.assert_called_once_with(UTC)
    assert calls.mock_calls == [call.run(session, date(2026, 10, 24)), call.commit()]
    assert "features_done day=2026-10-24 written=24" in caplog.text


def test_features_backfill_the_range_inclusive_one_commit_per_day(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, clock: Mock
) -> None:
    caplog.set_level("INFO", logger="pulso.ml")
    calls, session = run_features(monkeypatch, start="2026-09-29", end="2026-10-02")
    days = [date(2026, 9, 29), date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    assert calls.mock_calls == [c for day in days for c in (call.run(session, day), call.commit())]
    assert "features_done day=2026-10-02 written=2" in caplog.text


@pytest.mark.parametrize(
    "kwargs",
    [
        {"end": "2026-10-25"},  # today is still being collected
        {"start": "2026-10-02", "end": "2026-10-01"},
    ],
)
def test_features_refuse_an_unfinished_day_or_a_reversed_range(
    monkeypatch: pytest.MonkeyPatch, clock: Mock, kwargs: dict[str, str]
) -> None:
    monkeypatch.setenv("FEATURES_ENABLED", "on")
    get_session = Mock(side_effect=AssertionError("database touched"))
    monkeypatch.setattr(ml, "get_session", get_session)
    with pytest.raises(ValueError):
        app.tasks["ml.features"].apply(kwargs=kwargs, throw=True)
    get_session.assert_not_called()
