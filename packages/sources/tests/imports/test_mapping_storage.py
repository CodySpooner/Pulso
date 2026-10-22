from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, RawPayload, SearchTrend, Source
from pulso_core.settings import Settings
from pulso_sources.imports import ADAPTERS, commit_import, parse_csv, replay_import
from pulso_sources.storage import JsonValue, store_capture

from .conftest import FakeAdapter


@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize(
    "header,accepted",
    [
        ("Key", False),
        ("Token", False),
        ("Signature", False),
        ("Query", True),
        ("Author", False),
        ("Search Key", False),
    ],
)
def test_valid_mapping_replays_exactly_or_fails_before_capture(
    session: Session,
    settings: Settings,
    s3: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    header: str,
    accepted: bool,
    saved: bool,
) -> None:
    source = session.scalars(select(Source).where(Source.key == "google_trends")).one()
    mapping = {header: "keyword"}
    body = f"{header},date,interest\nlamp,2020-01-01,50\n".encode()
    assert parse_csv(source.key, body, mapping=mapping).rows[0]["keyword"] == "lamp"
    if saved:
        source.config = {"csv_mapping": mapping}
        session.commit()
    run = commit_import(
        session, source.key, body, settings=settings, mapping=None if saved else mapping
    )
    assert mapping == {header: "keyword"}
    if not accepted:
        assert run.status == "failed" and run.error_code == "ValueError"
        assert session.scalars(select(RawPayload)).all() == []
        assert session.scalars(select(SearchTrend)).all() == []
        s3.put_object.assert_not_called()
        s3.get_object.assert_not_called()
        return
    assert run.status == "success"
    payload = session.scalars(select(RawPayload)).one()
    assert payload.request["mapping"] == mapping
    source.config = {"csv_mapping": {header: "invalid"}}
    session.commit()
    monkeypatch.setitem(ADAPTERS, source.key, lambda data: FakeAdapter(data, "2"))
    replay = replay_import(session, payload.id, settings=settings)
    assert replay.status == "success" and replay.rows_inserted == 1
    observations = session.scalars(select(SearchTrend).order_by(SearchTrend.id)).all()
    assert [(row.keyword, row.parser_version) for row in observations] == [
        ("lamp", "1"),
        ("lamp", "2"),
    ]
    assert all(row.raw_payload_id == payload.id for row in observations)
    assert s3.put_object.call_count == 1


@pytest.mark.parametrize(
    "destination", ["not_a_template_column", "https://example.test/?token=FIXTURE"]
)
def test_mapping_destinations_still_require_template_validation(
    session: Session, settings: Settings, s3: MagicMock, destination: str
) -> None:
    run = commit_import(
        session,
        "google_trends",
        b"Query,date,interest\nlamp,2020-01-01,50\n",
        settings=settings,
        mapping={"Query": destination},
    )
    assert run.status == "failed" and run.error_code == "ValueError"
    assert session.scalars(select(RawPayload)).all() == []
    s3.put_object.assert_not_called()


@pytest.mark.parametrize("mapping", [{"Term": "keyword"}, {"Token": "FIXTURE"}])
def test_mapping_never_bypasses_arbitrary_metadata_redaction(
    session: Session, s3: MagicMock, mapping: dict[str, str]
) -> None:
    source = session.scalars(select(Source).where(Source.key == "google_trends")).one()
    run = CollectorRun(source_id=source.id, trigger="fixture")
    session.add(run)
    session.flush()
    request: dict[str, JsonValue] = {
        "mapping": dict(mapping),
        "headers": {"Authorization": "FIXTURE"},
        "response": {"private_token": "FIXTURE"},
        "nested": {"mapping": {"Signature": "FIXTURE"}},
    }
    if "Token" in mapping:
        with pytest.raises(ValueError, match="mapping"):
            store_capture(
                session,
                source_id=source.id,
                source_key=source.key,
                run_id=run.id,
                body=b"fixture",
                content_type="text/csv",
                status_code=None,
                etag=None,
                request=request,
                captured_at=datetime.now(UTC),
            )
        s3.put_object.assert_not_called()
        assert session.scalars(select(RawPayload)).all() == []
    else:
        payload = store_capture(
            session,
            source_id=source.id,
            source_key=source.key,
            run_id=run.id,
            body=b"fixture",
            content_type="text/csv",
            status_code=None,
            etag=None,
            request=request,
            captured_at=datetime.now(UTC),
        )
        assert payload.request == {
            "mapping": mapping,
            "headers": {},
            "response": {},
            "nested": {"mapping": {}},
        }
    assert request["headers"] == {"Authorization": "FIXTURE"}
