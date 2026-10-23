import io
import time
from collections.abc import Iterator
from datetime import UTC
from typing import Any
from unittest.mock import Mock

import pytest
from sqlalchemy import ARRAY, JSON, DateTime, Integer, MetaData, create_engine, event, text
from sqlalchemy.orm import Session, attributes
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import Listing, ListingSnapshot, RawPayload, Source
from pulso_sources import storage
from pulso_sources.cj import transport


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        transport, "HTTPSConnection", Mock(side_effect=AssertionError("No live HTTP"))
    )
    monkeypatch.setattr(transport, "_next_request", 0.0)
    monkeypatch.setattr(time, "sleep", lambda _: None)


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in (
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
        "suppliers",
        "listings",
        "listing_snapshots",
    ):
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, (JSON, ARRAY)):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        if name == "listings":
            for constraint in list(table.constraints):
                if isinstance(constraint.name, str) and constraint.name.endswith("one_vendor"):
                    table.constraints.remove(constraint)
        table.create(engine)
    objects: dict[str, bytes] = {}
    client = Mock()

    def put(**kwargs: Any) -> None:
        objects[kwargs["Key"]] = kwargs["Body"]

    client.put_object.side_effect = put
    client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", Mock())

    def utc(row: Any, *_: Any) -> None:
        for column in row.__table__.columns:
            value = row.__dict__.get(column.key)
            if isinstance(column.type, DateTime) and value is not None:
                attributes.set_committed_value(row, column.key, value.replace(tzinfo=UTC))

    for model in (Listing, ListingSnapshot, RawPayload):
        event.listen(model, "load", utc)
        event.listen(model, "refresh", utc)
    try:
        with Session(engine, expire_on_commit=False) as session:
            session.add(Source(id=2, key="cj", name="CJ", type="api", phase=1, enabled=False))
            session.commit()
            yield session
    finally:
        for model in (Listing, ListingSnapshot, RawPayload):
            event.remove(model, "load", utc)
            event.remove(model, "refresh", utc)
        engine.dispose()
