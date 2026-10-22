from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Barrier
from typing import Literal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, SearchTrend, Source
from pulso_core.settings import Settings
from pulso_sources.imports import ADAPTERS, TEMPLATES, commit_import, replay_import, template_csv

from .conftest import FakeAdapter


@pytest.mark.parametrize("key", TEMPLATES)
def test_every_template_commits_and_duplicate_skips_before_storage(
    session: Session, settings: Settings, s3: MagicMock, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = commit_import(session, key, template_csv(key), settings=settings)
    assert first.status == "success", first.error_message
    assert first.trigger == "csv" and first.rows_inserted == 1 and first.http_requests == 0
    payload = session.scalars(select(RawPayload)).one()
    assert payload.template_version == "csv-v1"
    target = session.get_one(CollectorRunTarget, (first.id, "import", str(payload.id)))
    assert target.status == "success"
    monkeypatch.delitem(ADAPTERS, key)
    second = commit_import(session, key, template_csv(key), settings=settings)
    assert second.status == "skipped" and second.rows_inserted == 0
    assert second.params["original_run_id"] == first.id
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 1
    assert session.scalar(select(func.count()).select_from(CollectorRun)) == 2
    assert s3.put_object.call_count == 1 and s3.get_object.call_count == 1


def test_multidate_file_valid_rows_only_and_saved_mapping(
    session: Session, settings: Settings, s3: MagicMock
) -> None:
    source = session.scalars(select(Source).where(Source.key == "google_trends")).one()
    source.config = {"csv_mapping": {"Term": "keyword", "Day": "date", "Value": "interest"}}
    session.commit()
    body = b"\xef\xbb\xbfTerm;Day;Value\na;2020-01-01;50\na;2020-01-02;30\nb;wrong;5\n"
    first = commit_import(session, source.key, body, settings=settings)
    assert first.status == "success" and first.rows_inserted == 2
    assert first.params["errors"] == [{"row": 4, "column": "date", "message": "Invalid date value"}]
    assert commit_import(session, source.key, body, settings=settings).status == "skipped"
    observations = list(session.scalars(select(SearchTrend).order_by(SearchTrend.observed_for)))
    assert [row.observed_for for row in observations] == [date(2020, 1, 1), date(2020, 1, 2)]
    assert all(row.captured_at.date() > row.observed_for for row in observations)
    assert len({row.raw_payload_id for row in observations}) == 1
    assert s3.put_object.call_count == 1


def test_identity_includes_template_version(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = template_csv("cj")
    assert commit_import(session, "cj", body, settings=settings).status == "success"
    monkeypatch.setitem(TEMPLATES, "cj", replace(TEMPLATES["cj"], template_version="csv-v2"))
    assert commit_import(session, "cj", body, settings=settings).status == "success"
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 2
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 2


def test_replay_uses_original_mapping_after_source_config_changes(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"Term,date,interest\nexample,2020-01-01,1\n"
    run = commit_import(
        session, "google_trends", body, settings=settings, mapping={"Term": "keyword"}
    )
    assert run.status == "success"
    source = session.get_one(Source, run.source_id)
    source.config = {"csv_mapping": {"Term": "invalid"}}
    session.commit()
    monkeypatch.setitem(ADAPTERS, source.key, lambda data: FakeAdapter(data, "2"))
    replay = replay_import(session, run.params["raw_payload_id"], settings=settings)
    assert replay.status == "success" and replay.rows_inserted == 1


@pytest.mark.parametrize("mode", ["csv", "json"])
def test_upload_timestamp_and_parser_correction_reuse_original_capture(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    mode: Literal["csv", "json"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = (
        template_csv("shopify_stores") if mode == "csv" else b'{"products":[{"keyword":"example"}]}'
    )
    before = datetime.now(UTC)
    run = commit_import(
        session,
        "shopify_stores",
        body,
        settings=settings,
        mode=mode,
        observed_for=date(2020, 1, 1),
    )
    after = datetime.now(UTC)
    assert run.status == "success", run.error_message
    payload = session.scalars(select(RawPayload)).one()
    original_at = payload.captured_at.replace(tzinfo=UTC)
    assert before <= original_at <= after
    observation = session.scalars(select(SearchTrend)).one()
    assert observation.observed_for == (date(2026, 1, 1) if mode == "csv" else date(2020, 1, 1))
    assert observation.captured_at.replace(tzinfo=UTC) == original_at
    assert replay_import(session, payload.id, settings=settings).status == "failed"
    monkeypatch.setitem(ADAPTERS, "shopify_stores", lambda data: FakeAdapter(data, "2"))
    replay = replay_import(session, payload.id, settings=settings)
    assert replay.status == "success", replay.error_message
    assert replay.rows_inserted == 1
    again = replay_import(session, payload.id, settings=settings)
    assert again.rows_inserted == 0 and again.rows_unchanged == 1
    rows = list(session.scalars(select(SearchTrend).order_by(SearchTrend.id)))
    assert [row.parser_version for row in rows] == ["1", "2"]
    assert [row.value for row in rows] == [1, 2]
    assert all(row.raw_payload_id == payload.id for row in rows)
    assert all(row.captured_at.replace(tzinfo=UTC) == original_at for row in rows)
    assert payload.run_id == run.id and s3.put_object.call_count == 1
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    duplicate = commit_import(
        session, "shopify_stores", body, settings=settings, mode=mode, observed_for=date(2000, 1, 1)
    )
    assert duplicate.status == "skipped" and s3.put_object.call_count == 1


@pytest.mark.parametrize(
    "body,observed",
    [
        (b"invalid", date(2020, 1, 1)),
        (b'{"products":[]}', None),
        (b'{"products":[], "bad":NaN}', date(2020, 1, 1)),
    ],
)
def test_invalid_json_records_failure_without_raw_storage(
    session: Session, settings: Settings, s3: MagicMock, body: bytes, observed: date | None
) -> None:
    run = commit_import(
        session, "shopify_stores", body, settings=settings, mode="json", observed_for=observed
    )
    assert run.status == "failed" and run.finished_at is not None
    assert not s3.put_object.called
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 0


def test_storage_and_adapter_failures_are_durable_and_sanitized(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_put = s3.put_object.side_effect
    s3.put_object.side_effect = RuntimeError("fixture-secret")
    run = commit_import(session, "cj", template_csv("cj"), settings=settings)
    assert run.status == "failed" and run.error_message == "RuntimeError"
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 0
    s3.put_object.side_effect = original_put
    monkeypatch.setattr(FakeAdapter, "parse", MagicMock(side_effect=ValueError("fixture-secret")))
    failed_parse = commit_import(session, "cj", template_csv("cj"), settings=settings)
    assert failed_parse.status == "partial" and failed_parse.error_message == "ValueError"
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 0


@pytest.mark.db
def test_concurrent_uploads_share_one_raw_capture(
    db_engine: Engine, settings: Settings, s3: MagicMock
) -> None:
    start = Barrier(2)

    def upload() -> str:
        with Session(db_engine) as connection:
            start.wait(timeout=10)
            return commit_import(connection, "cj", template_csv("cj"), settings=settings).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(upload) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == ["skipped", "success"]
    assert s3.put_object.call_count == 1
    with Session(db_engine) as connection:
        assert connection.scalar(select(func.count()).select_from(RawPayload)) == 1
