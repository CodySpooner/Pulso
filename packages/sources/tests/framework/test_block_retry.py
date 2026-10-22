import io
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, event, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import Source
from pulso_core.settings import Settings
from pulso_sources import framework, storage
from pulso_sources.framework import Request, Response, Target, enqueue_run, execute_run

from .test_lifecycle import FakeAdapter


@pytest.fixture
def session() -> Iterator[Session]:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in [
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
    ]:
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSON):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)
    try:
        with Session(engine) as session:
            session.add(
                Source(id=1, key="fixture", name="Fixture", type="api", phase=1, enabled=True)
            )
            session.commit()
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def network(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeAdapter, Mock, list[tuple[str, bool]]]:
    active = False
    calls: list[tuple[str, bool]] = []

    def begin(_: Connection) -> None:
        nonlocal active
        active = True

    def end(_: Connection) -> None:
        nonlocal active
        active = False

    engine = session.get_bind()
    event.listen(engine, "begin", begin)
    event.listen(engine, "commit", end)
    event.listen(engine, "rollback", end)
    client = MagicMock()
    objects: dict[str, bytes] = {}

    def put(**kwargs: Any) -> None:
        calls.append(("put", active))
        objects[kwargs["Key"]] = kwargs["Body"]

    def get(**kwargs: Any) -> dict[str, io.BytesIO]:
        calls.append(("get", active))
        return {"Body": io.BytesIO(objects[kwargs["Key"]])}

    responses = Mock(return_value=Response(b"ok", 200))

    def fetch(*args: Any, **kwargs: Any) -> Response:
        calls.append(("fetch", active))
        return responses(*args, **kwargs)  # type: ignore[no-any-return]

    client.put_object.side_effect, client.get_object.side_effect = put, get
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(FakeAdapter, "fetch", fetch)
    settings.collectors_live = True
    settings.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    return FakeAdapter(), responses, calls


def test_network_has_no_open_transaction(
    session: Session, settings: Settings, network: tuple[FakeAdapter, Mock, list[tuple[str, bool]]]
) -> None:
    adapter, _, calls = network
    run = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
    execute_run(session, run.id, adapter, [Target("catalog", "a", [Request()])], settings=settings)
    assert run.status == "success"
    assert calls == [("fetch", False), ("put", False), ("get", False)]
