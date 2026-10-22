import hashlib
import io
from collections.abc import Sequence
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, CollectorRunTarget, Listing, ListingSnapshot, RawPayload
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import (
    Request,
    Response,
    Target,
    UpsertStats,
    append_observation,
    enqueue_run,
    execute_run,
    lifecycle,
)


class DatabaseAdapter:
    parser_version = "1"

    def __init__(self, listing_id: int) -> None:
        self.listing_id = listing_id

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise AssertionError("No network in tests")

    def parse(self, body: bytes) -> Sequence[bytes]:
        return [body]

    def upsert(
        self,
        session: Session,
        records: Sequence[bytes],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        row = ListingSnapshot(
            listing_id=self.listing_id,
            raw_payload_id=payload.id,
            captured_at=payload.captured_at,
            observed_for=payload.captured_at.date(),
            parser_version=parser_version,
            values_hash=hashlib.sha256(records[0]).hexdigest(),
            currency="USD",
        )
        inserted = int(append_observation(session, row))
        if records[0] == b"broken":
            raise ValueError("upsert must roll back")
        return UpsertStats(inserted=inserted, unchanged=1 - inserted)


@pytest.mark.db
def test_committed_run_raw_evidence_and_atomic_payloads(
    db_engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = MagicMock()
    objects: dict[str, bytes] = {}
    client.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    with Session(db_engine) as session:
        listing = Listing(source_id=1, external_id="test", title="Test", url="https://example.test")
        session.add(listing)
        session.commit()

        def publish(run_id: int) -> None:
            with Session(db_engine) as reader:
                queued = reader.get_one(CollectorRun, run_id)
                assert queued.status == "queued" and queued.started_at is None

        run = enqueue_run(session, source_id=1, trigger="csv", publish=publish)
        adapter = DatabaseAdapter(listing.id)
        requests = [Request(mode="fixture", body=b"first"), Request(mode="fixture", body=b"broken")]
        run = execute_run(
            session, run.id, adapter, [Target("catalog", "a", requests)], settings=settings
        )
        assert run.status == "partial" and not run.complete
        assert run.started_at is not None and run.finished_at is not None
        assert run.queued_at <= run.started_at <= run.finished_at
        assert run.rows_inserted == run.rows_fetched == 1
        rows = list(session.scalars(select(ListingSnapshot)))
        captures = list(session.scalars(select(RawPayload)))
        assert len(rows) == 1 and len(captures) == 2
        assert rows[0].raw_payload_id == captures[0].id
        assert storage.read_capture(captures[0]) == b"first"
        assert storage.read_capture(captures[1]) == b"broken"
        target = session.get_one(CollectorRunTarget, (run.id, "catalog", "a"))
        assert target.status == "partial" and target.captured_at >= captures[1].captured_at
        execute_run(session, run.id, adapter, [], settings=settings)
        assert len(list(session.scalars(select(RawPayload)))) == 2

        unchanged = enqueue_run(session, source_id=1, trigger="csv", publish=publish)
        monkeypatch.setattr(lifecycle, "fetch", Mock(return_value=Response(None, 304)))
        execute_run(
            session,
            unchanged.id,
            adapter,
            [Target("inventory", "b", [Request(mode="fixture")])],
            settings=settings,
        )
        covered = session.get_one(CollectorRunTarget, (unchanged.id, "inventory", "b"))
        assert covered.status == "success" and covered.raw_payload_id is not None
        assert session.get_one(RawPayload, covered.raw_payload_id).storage_key is None
        assert len(list(session.scalars(select(ListingSnapshot)))) == 1
