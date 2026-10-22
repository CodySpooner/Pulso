from dataclasses import replace
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy import MetaData, func, select
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import FxRate, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources.framework import Request, Target, enqueue_run, execute_run
from pulso_sources.fx_frankfurter import FrankfurterAdapter, plan
from pulso_sources.imports import ADAPTERS, commit_import, template_csv


def test_fx_framework_fixture_capture_and_csv_replay(
    session: Session, s3: MagicMock, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    if session.get_bind().dialect.name == "sqlite":
        metadata = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(metadata)
        metadata.tables["fx_rates"].create(session.get_bind())
    monkeypatch.setitem(ADAPTERS, "fx_frankfurter", FrankfurterAdapter)
    fetch = MagicMock(side_effect=AssertionError("No HTTP"))
    monkeypatch.setattr(FrankfurterAdapter, "fetch", fetch)
    source = session.scalars(select(Source).where(Source.key == "fx_frankfurter")).one()
    body = b'[{"date":"2026-01-01","base":"USD","quote":"JPY","rate":150}]'
    daily = plan(session, date(2026, 10, 22))[0]
    failed = enqueue_run(session, source_id=source.id, trigger="fixture", publish=lambda _: None)
    requests = [
        replace(request, mode="fixture", body=b"broken" if i == 0 else body)
        for i, request in enumerate(daily.requests)
    ]
    failed = execute_run(
        session,
        failed.id,
        FrankfurterAdapter(),
        [replace(daily, requests=requests)],
        settings=settings,
    )
    assert failed.status == "partial"
    assert session.scalar(select(func.count()).select_from(FxRate)) == 0
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    for expected in [1, 0]:
        run = enqueue_run(session, source_id=source.id, trigger="fixture", publish=lambda _: None)
        run = execute_run(
            session,
            run.id,
            FrankfurterAdapter(),
            [Target("fx", "latest", [Request(mode="fixture", body=body)])],
            settings=settings,
        )
        assert run.status == "success" and run.rows_inserted == expected
        assert run.http_requests == 0
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 3
    body = template_csv("fx_frankfurter")
    first = commit_import(session, "fx_frankfurter", body, settings=settings)
    assert first.status == "success" and first.rows_inserted == 1
    assert commit_import(session, "fx_frankfurter", body, settings=settings).status == "skipped"
    row = session.get_one(FxRate, (date(2026, 1, 1), "USD", "JPY", "manual"))
    assert row.captured_at.date() > row.observed_for and not source.enabled
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 4
    fetch.assert_not_called()
