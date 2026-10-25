from unittest.mock import MagicMock, Mock

import pytest

from pulso_ml.matching import matcher
from pulso_sources.fx_frankfurter import rate_as_of
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
    match = Mock(return_value=matcher.Counts(5, 1, 2, 2, 3))
    monkeypatch.setattr(matcher, "match", match)
    app.tasks["ml.match"].apply(throw=True)
    match.assert_called_once_with(session.__enter__.return_value, rate_as_of)
    assert "scored=5 linked=1 queued=2 discarded=2 skipped_no_embedding=3" in caplog.text
