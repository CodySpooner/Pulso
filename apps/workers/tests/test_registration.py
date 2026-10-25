from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_core.settings import get_settings
from pulso_sources.framework import enqueue_run
from pulso_sources.fx_frankfurter import FrankfurterAdapter
from pulso_workers import tasks
from pulso_workers.celery_app import app


def test_worker_import_registers_fx_without_enabling_source(session: Session) -> None:
    source = session.get_one(Source, 1)
    source.key, source.enabled = "fx_frankfurter", False
    session.commit()
    app.loader.import_default_modules()
    plan = tasks.PLANS["fx_frankfurter"](session, source, "fx")
    assert isinstance(plan.adapter, FrankfurterAdapter)
    assert plan.wall_time_seconds == get_settings().fx_wall_time_seconds
    assert plan.targets[0].scope == "fx"
    assert not source.enabled
    with pytest.raises(ValueError):
        tasks.PLANS["fx_frankfurter"](session, source, "catalog")


@pytest.mark.parametrize("registered", [False, True])
def test_missing_adapter_and_disabled_source_fail_closed(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    registered: bool,
) -> None:
    factory = Mock()
    source = session.get_one(Source, 1)
    if registered:
        monkeypatch.setitem(tasks.PLANS, source.key, factory)
        source.enabled = False
    session.commit()
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    tasks.collect_run(run.id)
    session.refresh(run)
    assert run.status == "failed" and run.error_code == "source_unavailable"
    factory.assert_not_called()
