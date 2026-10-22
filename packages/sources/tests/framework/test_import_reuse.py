from datetime import UTC, datetime
from typing import Literal
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, RawPayload, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import Request, Target, execute_run, fetch

from .test_lifecycle import FakeAdapter


@pytest.mark.parametrize(
    "mode,source_id,storage_key,expected",
    [
        ("csv", 1, "original", "success"),
        ("json", 1, "original", "success"),
        ("fixture", 1, "original", "success"),
        ("csv", 2, "original", "failed"),
        ("json", 1, None, "failed"),
        ("live", 1, "original", "failed"),
    ],
)
def test_existing_capture_reuse_and_guards(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    mode: Literal["csv", "json", "fixture", "live"],
    source_id: int,
    storage_key: str | None,
    expected: str,
) -> None:
    run = CollectorRun(
        id=1,
        source_id=1,
        trigger="csv",
        status="running",
        queued_at=datetime.now(UTC),
        rows_fetched=0,
        rows_inserted=0,
        rows_updated=0,
        rows_unchanged=0,
        http_requests=0,
    )
    source = Source(id=1, key="fixture", enabled=False)
    payload = RawPayload(
        id=7, source_id=source_id, storage_key=storage_key, captured_at=datetime.now(UTC)
    )
    session = Mock(spec=Session)
    session.scalar.return_value = run
    session.get_one.side_effect = lambda model, _: source if model is Source else payload
    store, read = Mock(), Mock(return_value=b"fixture")
    monkeypatch.setattr(storage, "store_capture", store)
    monkeypatch.setattr(storage, "read_capture", read)
    result = execute_run(
        session,
        1,
        FakeAdapter(),
        [Target("import", "7", [Request(mode=mode, raw_payload_id=7)])],
        settings=settings,
    )
    assert result.status == expected and result.http_requests == 0
    store.assert_not_called()
    if expected == "success":
        read.assert_called_once_with(payload)
        assert result.rows_inserted == 1
    else:
        read.assert_not_called()
        assert result.error_code == "ValueError"


def test_fetch_rejects_live_reuse_before_network(settings: Settings) -> None:
    with pytest.raises(ValueError, match="offline"):
        fetch(FakeAdapter(), Request(mode="live", raw_payload_id=7), settings=settings)
