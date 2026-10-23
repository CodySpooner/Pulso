"""PostgreSQL smoke for the shared Shopify plan queries; SQLite accepts shapes PG rejects."""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, update
from sqlalchemy.orm import Session

from pulso_core.models import Source, Store, Workspace, WorkspaceTrackedStore
from pulso_core.settings import Settings
from pulso_sources import shopify_stores
from pulso_sources.framework import enqueue_run

pytestmark = pytest.mark.db


@pytest.fixture
def session(db_engine: Engine) -> Iterator[Session]:
    # Overrides the SQLite fixture, so io_mock runs against the migrated schema.
    with Session(db_engine, expire_on_commit=False) as session:
        workspace = Workspace(name="Fixture")
        session.add(workspace)
        entries = []
        for i, domain in enumerate(("first.test", "second.test"), 1):
            entries.append({"domain": domain, "name": domain, "enabled": True})
            session.add(Store(id=i, domain=domain, platform="shopify"))
        session.flush()
        tracked = [WorkspaceTrackedStore(workspace_id=workspace.id, store_id=i) for i in (1, 2)]
        session.add_all(tracked)
        seed = {
            "version": "seed_v1",
            "status": "approved",
            "decision": "DEC-011",
            "approved_on": datetime.now(UTC).date().isoformat(),
            "entries": entries,
        }
        session.execute(
            update(Source).where(Source.id == 1).values(enabled=True, config={"seed": seed})
        )
        session.commit()
        yield session


def test_collect_twice_on_postgres(session: Session, settings: Settings, io_mock: Any) -> None:
    # P1-35 L6: PostgreSQL rejects an inlined GROUP BY domain expression (fixed in 5bd8e90).
    for _ in range(2):
        queued = enqueue_run(session, source_id=1, trigger="manual", publish=lambda _: None)
        run = shopify_stores.collect(session, queued.id, settings=settings)
        assert (run.status, run.error_code) == ("success", None)
