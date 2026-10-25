"""data-07: the worker's CJ catalog plan, end to end through collect_run with fake HTTP."""

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, ListingSnapshot, RawPayload, Source
from pulso_sources.framework import enqueue_run
from pulso_workers import registration, tasks

from .test_cj import fixture
from .test_points_csv import live

BODIES = {"/product/getCategory": fixture("categories"), "/product/listV2": fixture("list_v2")}


def collect(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    trigger: str,
    bodies: dict[str, bytes] = BODIES,
) -> tuple[CollectorRun, list[str]]:
    cfg, sent = live(session, monkeypatch, bodies)
    source = session.get_one(Source, 2)
    seed = {
        "status": "approved",
        "decision": "DEC-011",
        "version": "seed_v1",
        "approved_on": "2026-10-20",
        "entries": [{"name": name, "enabled": True}],
    }
    source.config = {**source.config, "seed": seed}
    session.commit()
    monkeypatch.setattr(registration, "get_settings", lambda: cfg)
    monkeypatch.setattr(tasks, "get_settings", lambda: cfg)
    monkeypatch.setattr(tasks, "get_session", lambda: nullcontext(session))
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))
    slot = f"catalog:{datetime.now(UTC).date()}"
    run = enqueue_run(session, source_id=2, trigger=trigger, slot_key=slot, publish=lambda _: None)
    tasks.collect_run(run.id)
    session.expire_all()
    return session.get_one(CollectorRun, run.id), sent


@pytest.mark.parametrize("trigger", ["catchup", "schedule"])
def test_catchup_and_scheduled_catalog_reach_execute_run(
    session: Session, monkeypatch: pytest.MonkeyPatch, trigger: str
) -> None:
    run, sent = collect(session, monkeypatch, "Computer & Office", trigger)
    # One resolved category: the tree, then 10 listing-count, 2 newest and 3 US pages.
    assert sent == ["/product/getCategory"] + ["/product/listV2"] * 15
    assert (run.status, run.complete, run.error_code) == ("success", True, None)
    assert run.http_requests == 16 and run.params["cj_points_reserved"] == 15 * 50
    target = session.scalars(select(CollectorRunTarget)).one()
    assert (target.scope, target.status) == ("cj_category_resolution", "success")
    requests = [p.request["endpoint"] for p in session.scalars(select(RawPayload))]
    assert requests == sent
    # Every page repeats the two fixture products; observations are change-only.
    assert session.scalar(select(func.count()).select_from(ListingSnapshot)) == 2


def test_unresolved_seed_fails_inside_the_run_after_the_tree(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, sent = collect(session, monkeypatch, "Pet Supplies", "schedule")
    # The free tree request is the evidence; nothing paid is sent for an unresolved name.
    assert sent == ["/product/getCategory"] and "cj_points_reserved" not in run.params
    assert (run.status, run.error_code) == ("partial", "cj_category_unresolved")


def test_inactivity_on_the_tree_request_disables_cj(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    lapsed = json.dumps({"code": 1600014, "result": False, "message": "disabled"}).encode()
    bodies = {**BODIES, "/product/getCategory": lapsed}
    run, sent = collect(session, monkeypatch, "Computer & Office", "schedule", bodies)
    source = session.get_one(Source, 2)
    assert sent == ["/product/getCategory"] and run.error_code == "cj_api_disabled_inactivity"
    assert (source.enabled, source.status, source.disabled_reason) == (
        False,
        "blocked",
        "cj_api_disabled_inactivity",
    )
