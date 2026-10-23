import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from threading import Barrier
from typing import Any, Literal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, RawPayload, SearchTrend, Source
from pulso_core.settings import Settings
from pulso_sources import imports as import_service
from pulso_sources import storage
from pulso_sources.imports import (
    ADAPTERS,
    TEMPLATES,
    commit_import,
    preview_csv,
    replay_import,
    template_csv,
)

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


@pytest.mark.parametrize("key", ["shopify_stores", "cj"])
def test_multidate_entity_file_reports_duplicate_rows_before_storage(
    session: Session, settings: Settings, s3: MagicMock, key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = next(csv.DictReader(io.StringIO(template_csv(key).decode())))
    output = io.StringIO()
    writer = csv.DictWriter(output, example.keys())
    writer.writeheader()
    for day in (1, 2, 3):
        writer.writerow({**example, "observed_for": f"2026-10-0{day}"})
    body = output.getvalue().encode()
    classify = MagicMock(side_effect=AssertionError("Rejected file must not be classified"))
    preview = preview_csv(key, body, classify=classify)
    assert preview.rows == [] and preview.counts["invalid"] == 3
    assert {error.row for error in preview.errors} == {2, 3, 4}
    assert all("row " in error.message for error in preview.errors)
    monkeypatch.delitem(ADAPTERS, key)
    run = commit_import(session, key, body, settings=settings)
    assert run.status == "failed" and run.error_code == "DuplicateEntityRows"
    session.expire_all()
    assert {error["row"] for error in run.params["errors"]} == {2, 3, 4}
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 0
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 0
    s3.put_object.assert_not_called()


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


def test_reupload_after_failed_parse_retries_existing_capture_then_skips(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = template_csv("cj")
    parse = FakeAdapter.parse
    failures = [ValueError("transient")]

    def flaky(self: FakeAdapter, body: bytes) -> object:
        if failures:
            raise failures.pop()
        return parse(self, body)

    monkeypatch.setattr(FakeAdapter, "parse", flaky)
    first = commit_import(session, "cj", body, settings=settings)
    assert first.status == "partial"
    payload = session.scalars(select(RawPayload)).one()
    # DEC-064: an unchanged parser_version is still not a correction.
    assert replay_import(session, payload.id, settings=settings).status == "failed"
    retry = commit_import(session, "cj", body, settings=settings)
    assert retry.status == "success" and retry.rows_inserted == 1
    assert retry.params["raw_payload_id"] == payload.id
    again = commit_import(session, "cj", body, settings=settings)
    assert again.status == "skipped"
    assert again.params == {"raw_payload_id": payload.id, "original_run_id": retry.id}
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 1
    assert s3.put_object.call_count == 1


def test_reupload_does_not_duplicate_a_queued_or_running_run_on_the_capture(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The worker dies before claiming the run: the capture is committed, the run stays queued.
    monkeypatch.setattr(
        import_service, "execute_run", lambda s, run_id, *a, **k: s.get_one(CollectorRun, run_id)
    )
    body = template_csv("cj")
    first = commit_import(session, "cj", body, settings=settings)
    assert first.status == "queued"
    payload_id = session.scalars(select(RawPayload.id)).one()
    second = commit_import(session, "cj", body, settings=settings)
    assert second.status == "skipped"
    assert second.params == {
        "raw_payload_id": payload_id,
        "original_run_id": first.id,
        "reason": "in_progress",
    }
    first.status = "failed"  # e.g. abandoned-run recovery
    session.commit()
    retry = commit_import(session, "cj", body, settings=settings)
    assert retry.status == "queued" and retry.params["raw_payload_id"] == payload_id
    third = commit_import(session, "cj", body, settings=settings)
    assert third.status == "skipped" and third.params["original_run_id"] == retry.id
    assert s3.put_object.call_count == 1
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1


def test_retry_reads_outside_transactions_with_fresh_session(
    session: Session, settings: Settings, s3: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"Term,date,interest\nexample,2020-01-01,1\n"
    with monkeypatch.context() as failing:
        failing.setattr(FakeAdapter, "parse", MagicMock(side_effect=ValueError("transient")))
        first = commit_import(
            session, "google_trends", body, settings=settings, mapping={"Term": "keyword"}
        )
    assert first.status == "partial"
    payload = session.scalars(select(RawPayload)).one()
    payload_id, original_run_id = payload.id, payload.run_id
    captured_at, metadata = payload.captured_at.replace(tzinfo=UTC), payload.request
    session.commit()
    original_get = s3.get_object.side_effect
    transactions = []
    with Session(session.get_bind()) as fresh:

        def get(**kwargs: Any) -> Any:
            transactions.append(fresh.in_transaction())
            return original_get(**kwargs)

        s3.get_object.side_effect = get
        retry = commit_import(
            fresh, "google_trends", body, settings=settings, mapping={"Term": "invalid"}
        )
        assert retry.status == "success", retry.error_message
        assert transactions == [False, False]
        assert retry.params["raw_payload_id"] == payload_id
        row = fresh.scalars(select(SearchTrend)).one()
        assert row.keyword == "example" and row.observed_for == date(2020, 1, 1)
        assert row.raw_payload_id == payload_id
        assert row.captured_at.replace(tzinfo=UTC) == captured_at
        stored = fresh.scalars(select(RawPayload)).one()
        assert stored.run_id == original_run_id and stored.request == metadata
        assert stored.captured_at.replace(tzinfo=UTC) == captured_at
        duplicate = commit_import(fresh, "google_trends", body, settings=settings)
        assert duplicate.status == "skipped" and duplicate.params["original_run_id"] == retry.id
    assert s3.put_object.call_count == 1


@pytest.mark.parametrize(
    "preparing,contender", [("replay", "upload"), ("upload", "replay"), ("replay", "replay")]
)
def test_preparing_capture_excludes_another_executor(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    preparing: str,
    contender: str,
) -> None:
    body = template_csv("cj")
    with monkeypatch.context() as failing:
        failing.setattr(FakeAdapter, "parse", MagicMock(side_effect=ValueError("transient")))
        first = commit_import(session, "cj", body, settings=settings)
    assert first.status == "partial"
    payload_id = session.scalars(select(RawPayload.id)).one()
    session.commit()
    monkeypatch.setitem(ADAPTERS, "cj", lambda data: FakeAdapter(data, "2"))
    original_get = s3.get_object.side_effect
    transactions = []
    overlaps = []
    with Session(session.get_bind()) as fresh:

        def get(**kwargs: Any) -> Any:
            transactions.append(fresh.in_transaction())
            if len(transactions) == 1:
                with Session(session.get_bind()) as other:
                    nested = (
                        replay_import(other, payload_id, settings=settings)
                        if contender == "replay"
                        else commit_import(other, "cj", body, settings=settings)
                    )
                    overlaps.append((nested.status, nested.params))
            return original_get(**kwargs)

        s3.get_object.side_effect = get
        run = (
            replay_import(fresh, payload_id, settings=settings)
            if preparing == "replay"
            else commit_import(fresh, "cj", body, settings=settings)
        )
        assert run.status == "success", run.error_message
        assert overlaps == [
            (
                "skipped",
                {"raw_payload_id": payload_id, "original_run_id": run.id, "reason": "in_progress"},
            )
        ]
        assert transactions == [False, False]
        assert (run.rows_inserted, run.rows_unchanged) == (1, 0)
        assert fresh.scalar(select(func.count()).select_from(RawPayload)) == 1
        assert fresh.scalar(select(func.count()).select_from(SearchTrend)) == 1
        assert fresh.scalar(select(func.count()).select_from(CollectorRunTarget)) == 2
    assert s3.put_object.call_count == 1


@pytest.mark.parametrize("mode", ["csv", "json"])
def test_future_dates_cannot_enter_observations(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    mode: Literal["csv", "json"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = MagicMock(wraps=datetime)
    clock.now.return_value = datetime(2026, 1, 1, 23, 59, tzinfo=UTC)
    monkeypatch.setattr(import_service, "datetime", clock)
    body = template_csv("shopify_stores").replace(b"2026-01-01", b"2026-01-02")
    if mode == "json":
        body = b'{"products":[{"keyword":"future"}]}'
    run = commit_import(
        session,
        "shopify_stores",
        body,
        settings=settings,
        mode=mode,
        observed_for=date(2026, 1, 2) if mode == "json" else None,
    )
    assert run.status == "failed"
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 0
    if mode == "csv":
        assert run.error_code == "no_valid_rows" and run.params["invalid_rows"] == 1
        payload = session.get_one(RawPayload, run.params["raw_payload_id"])
        assert payload.captured_at.replace(tzinfo=UTC) == clock.now.return_value
    else:
        s3.put_object.assert_not_called()


@pytest.mark.parametrize("mode", ["csv", "json"])
def test_replay_validates_dates_against_original_capture(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    mode: Literal["csv", "json"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Legacy evidence captured before the date bound existed; today's date cannot legalize it.
    source = session.scalars(select(Source).where(Source.key == "shopify_stores")).one()
    original = CollectorRun(source_id=source.id, trigger="csv", status="failed")
    session.add(original)
    session.flush()
    body = template_csv(source.key) if mode == "csv" else b'{"products":[{"keyword":"future"}]}'
    payload = storage.store_capture(
        session,
        source_id=source.id,
        source_key=source.key,
        run_id=original.id,
        body=body,
        content_type="text/csv" if mode == "csv" else "application/json",
        status_code=None,
        etag=None,
        captured_at=datetime(2025, 12, 31, tzinfo=UTC),
        request={"mode": mode, "mapping": {}, "parser_version": "1", "observed_for": "2026-01-01"},
    )
    payload.template_version = "csv-v1" if mode == "csv" else "shopify-json-v1"
    session.commit()
    monkeypatch.setitem(ADAPTERS, source.key, lambda data: FakeAdapter(data, "2"))
    replay = replay_import(session, payload.id, settings=settings)
    assert replay.status == "failed"
    assert session.scalar(select(func.count()).select_from(SearchTrend)) == 0
    assert s3.put_object.call_count == 1
    if mode == "csv":
        assert replay.params["errors"][0]["column"] == "observed_for"


@pytest.mark.parametrize("duplicates", [False, True])
def test_persisted_errors_are_bounded_but_counts_are_complete(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    duplicates: bool,
) -> None:
    body = (
        b"sku,name,unit_cost\n" + b"SKU,Example,1\n" * 100_000
        if duplicates
        else b"keyword,date,interest\n" + b"a,invalid,101\n" * 100_000
    )
    run = commit_import(session, "cj" if duplicates else "google_trends", body, settings=settings)
    session.expire_all()
    assert run.status == "failed" and len(run.params["errors"]) == 100
    assert run.params["invalid_rows"] == 100_000
    assert run.params["error_count"] == (100_000 if duplicates else 200_000)
    assert run.params["errors_by_column"] == (
        {"sku": 100_000} if duplicates else {"date": 100_000, "interest": 100_000}
    )
    assert len(json.dumps(run.params).encode()) < 64 * 1024


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
