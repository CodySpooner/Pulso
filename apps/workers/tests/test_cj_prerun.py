"""data-07: a CJ catch-up reaches execute_run, and every pre-run failure has its own code."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, HostHeartbeat, Source
from pulso_core.settings import get_settings
from pulso_sources.framework import lifecycle
from pulso_workers import ops, registration, tasks

NOW = datetime(2026, 10, 25, 17, 10, tzinfo=UTC)  # Sunday; d341e64 enabled cj at 17:09:42Z
SEED = {
    "status": "approved",
    "decision": "DEC-011",
    "version": "seed_v1",
    "approved_on": "2026-10-20",
    "entries": [{"name": "Pet Supplies", "enabled": True}],
}


@pytest.fixture
def cj(session: Session, monkeypatch: pytest.MonkeyPatch) -> Source:
    assert registration  # importing it registers the worker plans, as the worker does
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    clock = Mock(wraps=datetime)
    clock.now.return_value = NOW
    for module in (ops, tasks, lifecycle):
        monkeypatch.setattr(module, "datetime", clock)
    source = session.get_one(Source, 1)
    source.key, source.status, source.config = "cj", "active", {"seed": SEED}
    session.add(HostHeartbeat(host="collector", at=NOW - timedelta(minutes=5)))
    session.commit()
    return source


def test_catchup_after_enable_reaches_execute_run(session: Session, cj: Source) -> None:
    ops.heartbeat()  # the 17:10Z heartbeat audit that queued the failed run
    run = session.scalars(select(CollectorRun)).one()
    # d341e64 picked freight:2026-W43 (Monday's slot) first; freight is unscheduled (DEC-321b).
    assert (run.trigger, run.status, run.slot_key) == ("catchup", "queued", "catalog:2026-10-25")
    tasks.collect_run(run.id)
    session.refresh(run)
    # d341e64: failed before execute_run with started_at null and error_code ValueError.
    assert run.started_at is not None
    # COLLECTORS_LIVE is off here, so the CJ guard stops the run before any request.
    assert (run.error_code, run.http_requests) == ("CollectorsLiveDisabled", 0)


def queued(session: Session, slot: str | None = "catalog:2026-10-25") -> CollectorRun:
    run = CollectorRun(source_id=1, trigger="schedule", slot_key=slot, status="queued")
    session.add(run)
    session.commit()
    tasks.collect_run(run.id)
    session.refresh(run)
    assert run.status == "failed" and run.started_at is None
    return run


@pytest.mark.parametrize("key", ["cj", "no_plan"])
def test_source_unavailable(session: Session, cj: Source, key: str) -> None:
    cj.key, cj.enabled = key, key != "cj"
    session.commit()
    run = queued(session)
    assert (run.error_code, run.error_message) == (
        "source_unavailable",
        "Source disabled or adapter unavailable",
    )


def test_unknown_job(session: Session, cj: Source) -> None:
    run = queued(session, "freight:2026-W43")  # the row the host's 17:10Z catch-up left
    assert (run.error_code, run.error_message) == (
        "unknown_job",
        "Source has no plan for this job",
    )


def test_plan_failed(session: Session, cj: Source) -> None:
    cj.config = {"seed": {**SEED, "status": "draft"}}  # no approved category names
    session.commit()
    run = queued(session)
    assert (run.error_code, run.error_message) == ("plan_failed", "Plan failed: ValueError")


def test_plan_budget_invalid(session: Session, cj: Source, monkeypatch: pytest.MonkeyPatch) -> None:
    over = get_settings().model_copy(update={"cj_wall_time_seconds": 10**6})  # unvalidated
    monkeypatch.setattr(registration, "get_settings", lambda: over)
    run = queued(session)  # fixed text: neither budget value reaches the stored message
    assert (run.error_code, run.error_message) == (
        "plan_budget_invalid",
        "Plan budget must be positive and below soft limit",
    )
