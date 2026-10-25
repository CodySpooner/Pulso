"""data-07: the worker's CJ catalog plan, end to end through collect_run with fake HTTP."""

import json
from contextlib import nullcontext
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    ListingSnapshot,
    RawPayload,
    Source,
    SourceEvent,
)
from pulso_sources import cj
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import Response, enqueue_run
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


BLOCKED = json.dumps({"code": 1600200, "result": False, "message": "Too much request"}).encode()


def catalog(
    session: Session, monkeypatch: pytest.MonkeyPatch, responses: dict[str, Response]
) -> tuple[CollectorRun, list[str]]:
    cfg, sent = live(session, monkeypatch, {})

    def http(self: Transport, endpoint: str, params: object, *, token: str | None) -> Response:
        sent.append(endpoint)
        return responses[endpoint]

    monkeypatch.setattr(Transport, "http", http)
    adapter = cj.CatalogAdapter(["Computer & Office"])
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    return cj.collect(session, run.id, adapter.targets(), settings=cfg, adapter=adapter), sent


@pytest.mark.parametrize(
    "blocked",
    [Response(BLOCKED, 200), Response(BLOCKED, 429, headers={"Retry-After": "60"})],
)
def test_free_tree_never_resets_the_paid_block_streak(
    session: Session, monkeypatch: pytest.MonkeyPatch, blocked: Response
) -> None:
    """XR-59: a 200 tree each run must not hide blocked listV2 calls from DEC-032."""
    tree = Response(BODIES["/product/getCategory"], 200)
    for count in range(1, 6):
        run, sent = catalog(
            session, monkeypatch, {"/product/getCategory": tree, "/product/listV2": blocked}
        )
        source = session.get_one(Source, 2)
        assert sent == ["/product/getCategory", "/product/listV2"]
        assert run.error_code == "cj_rate_limited" and source.consecutive_block_count == count
        assert source.enabled == (count < 5)
        if blocked.status_code == 429:
            assert source.retry_not_before is not None
            source.retry_not_before = None  # The Retry-After has passed before the next slot.
            session.commit()
    assert source.status == "blocked"
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1


@pytest.mark.parametrize("blocked", [Response(BLOCKED, 200), Response(BLOCKED, 429)])
def test_blocked_tree_answer_still_counts(
    session: Session, monkeypatch: pytest.MonkeyPatch, blocked: Response
) -> None:
    session.get_one(Source, 2).consecutive_block_count = 2
    run, sent = catalog(session, monkeypatch, {"/product/getCategory": blocked})
    assert sent == ["/product/getCategory"] and run.error_code == "cj_rate_limited"
    assert session.get_one(Source, 2).consecutive_block_count == 3


def test_successful_list_page_still_resets_the_streak(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    session.get_one(Source, 2).consecutive_block_count = 4
    run, _ = catalog(session, monkeypatch, {k: Response(v, 200) for k, v in BODIES.items()})
    assert run.status == "success" and session.get_one(Source, 2).consecutive_block_count == 0
