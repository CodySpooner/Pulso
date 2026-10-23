import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import Source
from pulso_core.settings import Settings, get_settings
from pulso_workers import beat, ops, tasks
from pulso_workers.celery_app import app


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setattr(logging.getLogger("pulso"), "propagate", True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(beat, "__file__", str(tmp_path / "installed" / "beat.py"))
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    metadata = MetaData()
    engine = create_engine("sqlite://")
    for name in (
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "host_heartbeats",
        "collection_gaps",
        "currencies",
        "fx_rates",
    ):
        table = Base.metadata.tables[name].to_metadata(metadata)
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSON):
                column.type, column.server_default = JSON(), DefaultClause(text("'{}'"))
        for index in table.indexes:
            if index.dialect_options["postgresql"].get("where") is not None:
                index.dialect_options["sqlite"]["where"] = index.dialect_options["postgresql"][
                    "where"
                ]
        table.create(engine)
    with Session(engine) as session:
        session.add(Source(id=1, key="fixture", name="Fixture", type="api", phase=1, enabled=True))
        session.commit()
        monkeypatch.setattr(tasks, "get_session", lambda: Session(engine))
        monkeypatch.setattr(ops, "get_session", lambda: Session(engine))
        monkeypatch.setattr(ops, "is_linked_worktree", lambda _: False)
        monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))
        monkeypatch.setattr(ops, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))
        monkeypatch.setattr(app, "send_task", Mock())
        yield session
    engine.dispose()
