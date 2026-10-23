import io
import json
import sqlite3
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import ARRAY, JSON, Integer, MetaData, create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, attributes
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import Source, Store, WorkspaceTrackedStore
from pulso_core.settings import Settings
from pulso_sources import framework, shopify_stores, storage
from pulso_sources.framework import Response

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> Response:
    data = json.loads((FIXTURES / f"{name}.json").read_text())
    body = data["body"]
    return Response(
        (json.dumps(body) if isinstance(body, dict) else body).encode(),
        data["status"],
        data.get("content_type", "application/json"),
        data.get("headers", {}).get("ETag"),
        headers=data.get("headers", {}),
    )


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        s3_access_key_id="fixture",
        s3_secret_access_key="fixture",
        collectors_live=True,
        pulso_bot_contact="https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md",
    )


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    adapters: Any = sqlite3.adapters
    monkeypatch.setitem(adapters, (list, sqlite3.PrepareProtocol), json.dumps)
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.connection.create_function(
            "num_nonnulls", -1, lambda *xs: sum(x is not None for x in xs)
        )
    for name in (
        "sources",
        "stores",
        "workspace_tracked_stores",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
        "listings",
        "listing_variants",
        "listing_snapshots",
        "variant_snapshots",
        "images",
    ):
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, (JSONB, ARRAY)):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        seed: dict[str, Any] = {
            "version": "seed_v1",
            "status": "approved",
            "decision": "DEC-011",
            "approved_on": datetime.now(UTC).date().isoformat(),
            "entries": [],
        }
        for i, domain in enumerate(("first.test", "second.test", "inspireuplift.com"), 1):
            seed["entries"].append({"domain": domain, "name": domain, "enabled": True})
            session.add(Store(id=i, domain=domain, platform="shopify"))
            session.add(WorkspaceTrackedStore(workspace_id=uuid4(), store_id=i))
        session.add(
            Source(
                id=1,
                key="shopify_stores",
                name="Shopify",
                type="crawler",
                phase=1,
                enabled=True,
                config={"seed": seed},
            )
        )
        session.commit()

        def utc(source: Source, *_: Any) -> None:
            if source.retry_not_before:
                attributes.set_committed_value(
                    source, "retry_not_before", source.retry_not_before.replace(tzinfo=UTC)
                )

        event.listen(Source, "refresh", utc)
        try:
            yield session
        finally:
            event.remove(Source, "refresh", utc)
    engine.dispose()


@pytest.fixture
def io_mock(monkeypatch: pytest.MonkeyPatch, settings: Settings, session: Session) -> Any:
    objects: dict[str, bytes] = {}
    s3 = Mock()
    s3.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: s3)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(shopify_stores, "_next_global", 0)
    monkeypatch.setattr(shopify_stores, "_next_store", {})
    state: Any = Mock(now=100.0, calls=[], replies={})
    monkeypatch.setattr(time, "monotonic", lambda: state.now)
    monkeypatch.setattr(time, "sleep", lambda seconds: setattr(state, "now", state.now + seconds))

    def open_url(request: Any, *, timeout: int) -> Any:
        assert not session.in_transaction()
        url = request.full_url
        state.calls.append((url, state.now, dict(request.header_items())))
        response = state.replies[url]  # Unscripted HTTP is always a test failure.
        if isinstance(response, BaseException):
            raise response
        result = io.BytesIO(response.body or b"")
        result.code = response.status_code  # type: ignore[attr-defined]
        result.headers = {"Content-Type": response.content_type, **response.headers}  # type: ignore[attr-defined]
        return result

    monkeypatch.setattr(shopify_stores, "build_opener", lambda *args: Mock(open=open_url))
    for i, domain in enumerate(("first.test", "second.test"), 1):
        origin = f"https://{domain}"
        state.replies[origin + "/robots.txt"] = fixture("robots")
        meta = json.loads(fixture("meta").body or b"")
        meta["id"] = i
        state.replies[origin + "/meta.json"] = Response(json.dumps(meta).encode(), 200)
        state.replies[origin + "/products.json?limit=250&page=1"] = fixture("normal")
    return state
