import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, ListingSnapshot, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources.cj import CJAdapter
from pulso_sources.cj.budget import reserve
from pulso_sources.cj.errors import CJError
from pulso_sources.framework import Request, Target, enqueue_run, execute_run

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
    reserve(session, session.get_one(Source, 2), run, "/product/listV2", settings=cfg, now=AT)
    session.commit()
    with Session(session.get_bind()) as later:
        source, previous = later.get_one(Source, 2), later.get_one(CollectorRun, run.id)
        with pytest.raises(CJError):
            reserve(later, source, previous, "/product/listV2", settings=cfg, now=AT)
        later.rollback()
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
