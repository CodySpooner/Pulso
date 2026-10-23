import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
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
from pulso_core.settings import Settings
from pulso_sources import framework
from pulso_sources.cj import CJAdapter, collect
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.budget import record_points, reserve
from pulso_sources.cj.errors import CJError
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import (
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    enqueue_run,
    execute_run,
)

BODY = (Path(__file__).parent / "fixtures/list_v2.json").read_bytes()
ERRORS = json.loads((Path(__file__).parent / "fixtures/errors.json").read_bytes())[:4]
AT = datetime(2026, 10, 22, tzinfo=UTC)


def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://fixture"),
        s3_access_key_id="fixture",
        s3_secret_access_key=SecretStr("fixture"),
    )


def test_fixture_run_replay_and_parser_correction(session: Session) -> None:
    adapter = CJAdapter()
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        adapter,
        [Target("cj_catalog_panel", "fixture", [Request(mode="fixture", body=BODY)])],
        settings=settings(),
    )
    assert run.status == "success" and run.complete and run.http_requests == 0
    assert run.rows_inserted == 2
    payload = session.scalars(select(RawPayload)).one()
    evidence = session.scalars(select(CollectorRunTarget)).one()
    assert evidence.raw_payload_id == payload.id and evidence.status == "success"
    records = adapter.parse(BODY)
    assert (
        adapter.upsert(session, records, payload, parser_version=adapter.parser_version).inserted
        == 0
    )
    assert adapter.upsert(session, records, payload, parser_version="cj-catalog-v2").inserted == 2
    session.commit()
    assert session.scalar(select(func.count()).select_from(ListingSnapshot)) == 4
    rows = list(session.scalars(select(ListingSnapshot)))
    assert all(row.sold_count is None and row.stock is None for row in rows)
    assert not session.get_one(Source, 2).enabled


def test_budget_survives_new_session_and_rolls_over(session: Session) -> None:
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    cfg = settings()
    cfg.cj_daily_points_budget = 50
    record_points(session.get_one(Source, 2), BODY, AT)
    session.commit()
    reserve(session, session.get_one(Source, 2), run, "/product/listV2", settings=cfg, now=AT)
    session.commit()
    with Session(session.get_bind()) as later:
        source, previous = later.get_one(Source, 2), later.get_one(CollectorRun, run.id)
        with pytest.raises(CJError):
            reserve(later, source, previous, "/product/listV2", settings=cfg, now=AT)
        later.rollback()
        record_points(source, BODY, AT + timedelta(days=1))
        later.commit()
        reserve(
            later, source, previous, "/product/listV2", settings=cfg, now=AT + timedelta(days=1)
        )
        later.commit()
        assert source.config["cj_points"] == {"day": "2026-10-23", "reserved": 50}
        assert previous.params["cj_points_reserved"] == 100


@pytest.mark.parametrize("case", ERRORS)
def test_error_fixture_reaches_data_health_and_stops_plan(
    session: Session, case: dict[str, object]
) -> None:
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    execute_run(
        session,
        run.id,
        CJAdapter(),
        [
            Target(
                "cj_catalog_panel",
                "bad",
                [Request(mode="fixture", body=json.dumps(case["body"]).encode())],
            ),
            Target("cj_catalog_panel", "next", [Request(mode="fixture", body=BODY)]),
        ],
        settings=settings(),
    )
    assert run.error_code == case["expected"] and run.status == "partial"
    assert run.rows_inserted == 0 and not run.complete
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    source = session.get_one(Source, 2)
    assert not source.enabled and source.consecutive_block_count == 0


@pytest.mark.parametrize("case", ERRORS)
def test_mock_http_reserves_before_send_and_persists_cj_error(
    session: Session, monkeypatch: pytest.MonkeyPatch, case: dict[str, object]
) -> None:
    cfg = settings()
    cfg.collectors_live = True
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)

    def fake_fetch(*args: object, **kwargs: object) -> Response:
        assert not session.in_transaction()
        assert source.config["cj_points"]["reserved"] == 50
        return Response(json.dumps(case["body"]).encode(), int(str(case["status"])))

    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    monkeypatch.setattr(Transport, "http", fake_fetch)
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session,
        run.id,
        [
            Target(
                "cj_catalog_panel",
                "fixture",
                [
                    Request(params={"endpoint": "/product/listV2"}),
                    Request(params={"endpoint": "/product/listV2"}),
                ],
            )
        ],
        settings=cfg,
    )
    assert run.error_code == case["expected"] and run.http_requests == 1
    assert run.status == "partial" and run.params["cj_points_reserved"] == 50
    assert source.enabled == (
        case["expected"] not in {"cj_ip_user_limit", "cj_api_disabled_inactivity"}
    )
    assert source.consecutive_block_count == int(case["status"] == 429)
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == int(not source.enabled)


def test_budget_stops_before_next_request(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = settings()
    cfg.collectors_live, cfg.cj_daily_points_budget = True, 50
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    monkeypatch.setattr(Transport, "http", lambda *a, **kw: Response(BODY, 200))
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    requests = [Request(params={"endpoint": "/product/listV2"})] * 2
    collect(session, run.id, [Target("cj_catalog_panel", "fixture", requests)], settings=cfg)
    assert run.status == "partial" and run.error_code == "cj_daily_budget"
    assert run.http_requests == 1 and run.rows_inserted == 2
    assert source.enabled and source.consecutive_block_count == 0


@pytest.mark.parametrize("live,worktree", [(False, False), (True, True)])
def test_refused_attempt_reserves_nothing(
    session: Session, monkeypatch: pytest.MonkeyPatch, live: bool, worktree: bool
) -> None:
    cfg = settings()
    cfg.collectors_live = live
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: worktree)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: worktree)
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    with pytest.raises(CollectorsLiveDisabled):
        collect(
            session,
            run.id,
            [
                Target(
                    "cj_catalog_panel", "fixture", [Request(params={"endpoint": "/product/listV2"})]
                )
            ],
            settings=cfg,
        )
    assert run.http_requests == 0 and "cj_points" not in source.config


@pytest.mark.parametrize("code", [1600200, 16900500])
def test_body_block_codes_accumulate_without_changing_http_evidence(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    code: int,
) -> None:
    cfg = settings()
    cfg.collectors_live, cfg.collector_block_threshold = True, 2
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    monkeypatch.setattr(
        Transport,
        "http",
        lambda *a, **kw: Response(
            json.dumps(
                {
                    "code": code,
                    "result": False,
                    "pointsInfo": json.loads(BODY)["pointsInfo"],
                }
            ).encode(),
            200,
        ),
    )
    for count in (1, 2):
        run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
        collect(
            session,
            run.id,
            [
                Target(
                    "cj_catalog_panel", "fixture", [Request(params={"endpoint": "/product/listV2"})]
                )
            ],
            settings=cfg,
        )
        assert source.consecutive_block_count == count and run.last_status_code == 200
    assert not source.enabled
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1
    assert all(p.status_code == 200 for p in session.scalars(select(RawPayload)))
