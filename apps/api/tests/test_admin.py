import asyncio
import gzip
import io
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import (
    JSON,
    Column,
    Date,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import DefaultClause

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.admin import get_publisher, get_source
from pulso_core.db import Base
from pulso_core.logging import JsonFormatter
from pulso_core.models import (
    CollectionGap,
    CollectorRun,
    CollectorRunTarget,
    HostHeartbeat,
    RawPayload,
    Source,
    SourceEvent,
)
from pulso_core.settings import Settings, get_settings
from pulso_sources import storage
from pulso_sources.framework import (
    Request,
    Response,
    Target,
    UpsertStats,
    enqueue_run,
    execute_run,
)
from pulso_sources.imports import ADAPTERS, ImportData, Row, template_csv
from pulso_sources.imports.csv import MAX_BYTES

NOW = datetime.now(UTC).replace(microsecond=0)
PRINCIPAL = Principal(uuid4(), uuid4())
SOURCES = {
    "shopify_stores": "public_endpoint",
    "cj": "official_api",
    "google_trends": "vendor",
    "fx_frankfurter": "official_api",
    "backup": "internal",
}
ROUTES = [
    ("GET", "/v1/admin/sources"),
    ("PATCH", "/v1/admin/sources/cj"),
    ("POST", "/v1/admin/sources/cj/run"),
    ("GET", "/v1/admin/runs"),
    ("GET", "/v1/admin/runs/1"),
    ("GET", "/v1/admin/coverage"),
    ("GET", "/v1/admin/host"),
    ("GET", "/v1/admin/sources/cj/import/template"),
    ("POST", "/v1/admin/sources/cj/import/preview"),
    ("POST", "/v1/admin/sources/cj/import"),
]


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.db)])
def engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    if request.param == "postgres":
        yield request.getfixturevalue("db_engine")  # migrations seed the same sources
        return
    # SQLite checks the queries offline; Postgres owns the real view, constraints and UTC.
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        for column in table.to_metadata(metadata).columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSONB):
                column.type, column.server_default = JSON(), DefaultClause(text("'{}'"))
    Table(  # stands in for the Postgres-only source_daily_coverage view
        "source_daily_coverage",
        metadata,
        *(Column(name, Integer) for name in ("source_id", "runs", "rows", "targets")),
        Column("successful_targets", Integer),
        Column("day", Date),
        Column("status", String),
    )
    names = ["sources", "collector_runs", "raw_payloads", "collector_run_targets"]
    names += ["host_heartbeats", "collection_gaps", "source_events", "source_daily_coverage"]
    offline = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    metadata.create_all(offline, tables=[metadata.tables[name] for name in names])
    with Session(offline) as session:
        session.add_all(
            Source(id=i, key=key, name=key, type=kind, phase=1)
            for i, (key, kind) in enumerate(SOURCES.items(), 1)
        )
        session.commit()
    yield offline
    offline.dispose()


@pytest.fixture
def admin(client: TestClient, engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: PRINCIPAL
    return client


def naive(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def record(engine: Engine, source_id: int, at: datetime, **targets: str) -> int:
    """One finished run whose targets succeed (304 evidence) or fail."""
    with Session(engine) as session:
        status = "success" if all(s == "success" for s in targets.values()) else "failed"
        run = CollectorRun(source_id=source_id, trigger="schedule", status=status, queued_at=at)
        session.add(run)
        session.flush()
        payload = RawPayload(
            source_id=source_id, run_id=run.id, request={}, bytes=0, sha256="0" * 64
        )
        session.add(payload)
        session.flush()
        session.add_all(
            CollectorRunTarget(
                run_id=run.id,
                scope="store",
                target_id=target,
                status=state,
                raw_payload_id=payload.id if state == "success" else None,
                captured_at=at,
            )
            for target, state in targets.items()
        )
        session.commit()
        return run.id


@pytest.mark.parametrize("method,path", ROUTES)
def test_admin_routes_reject_non_admins(
    client: TestClient, signed_token: Callable[[dict[str, Any]], str], method: str, path: str
) -> None:
    token = signed_token({"sub": "user_other"})
    response = client.request(method, path, headers={"Authorization": "Bearer " + token})
    assert response.status_code == 403
    assert response.json()["code"] == "not_allowlisted"


def test_freshness_survives_unrelated_target_failure(admin: TestClient, engine: Engine) -> None:
    first = record(engine, 2, NOW - timedelta(days=2), a="success", b="success")
    last = record(engine, 2, NOW - timedelta(days=1), b="failed")
    sources = {source["key"]: source for source in admin.get("/v1/admin/sources").json()}
    assert list(sources) == list(SOURCES)
    cj = sources["cj"]
    assert naive(cj["freshness"]) == (NOW - timedelta(days=2)).replace(tzinfo=None)
    assert cj["last_run"]["id"] == last
    assert (cj["last_run"]["target_count"], cj["last_run"]["successful_target_count"]) == (1, 0)
    assert (cj["seed_approved"], cj["approved_targets"], cj["quota_used"]) == (False, 0, None)
    assert "config" not in cj
    never = sources["fx_frankfurter"]
    assert (never["last_run"], never["freshness"], never["seed_approved"]) == (None, None, None)

    page = admin.get("/v1/admin/runs", params={"source": "cj", "limit": 1}).json()
    assert [run["id"] for run in page["items"]] == [last]
    older = admin.get("/v1/admin/runs", params={"source": "cj", "cursor": page["next_cursor"]})
    assert [run["id"] for run in older.json()["items"]] == [first]
    assert older.json()["next_cursor"] is None
    assert admin.get("/v1/admin/runs", params={"source": "backup"}).json()["items"] == []
    unknown = admin.get("/v1/admin/runs", params={"source": "no_such_source"})
    assert (unknown.status_code, unknown.json()) == (200, {"items": [], "next_cursor": None})

    detail = admin.get(f"/v1/admin/runs/{first}").json()
    assert [(t["target_id"], t["status"]) for t in detail["targets"]] == [
        ("a", "success"),
        ("b", "success"),
    ]
    assert all(isinstance(t["raw_payload_id"], int) for t in detail["targets"])
    assert admin.get("/v1/admin/runs/999").status_code == 404


@pytest.mark.parametrize("limit", [1, 2, 4])
def test_source_run_pages_keep_id_order_with_interleaved_sources(
    admin: TestClient, engine: Engine, limit: int
) -> None:
    expected: list[int] = []
    for source_id in (2, 1, 5, 2, 1, 2, 5):
        run_id = record(engine, source_id, NOW, a="success")
        if source_id == 2:
            expected.insert(0, run_id)
    params: dict[str, str | int] = {"source": "cj", "limit": limit}
    seen: list[int] = []
    for _ in range(len(expected)):
        response = admin.get("/v1/admin/runs", params=params)
        assert response.status_code == 200
        page = response.json()
        assert all(run["source_key"] == "cj" for run in page["items"])
        seen.extend(run["id"] for run in page["items"])
        if page["next_cursor"] is None:
            break
        params["cursor"] = page["next_cursor"]
    assert page["next_cursor"] is None
    assert seen == expected


def test_blocked_by_comes_only_from_slot_suppressed_evidence(
    admin: TestClient, engine: Engine
) -> None:
    """imp-042 (DEC-123): a suppressed slot names its blocker; every other run reads null."""
    blocker = record(engine, 2, NOW - timedelta(hours=1), a="success")
    with Session(engine) as session:
        runs = [
            CollectorRun(source_id=2, trigger="schedule", status="skipped", queued_at=NOW, **extra)
            for extra in (
                {"params": {"blocked_by": 7}},  # not slot_suppressed: never read
                {"params": {}, "error_code": "slot_suppressed"},  # evidence missing: stays null
                {"params": {"blocked_by": blocker}, "error_code": "slot_suppressed"},
            )
        ]
        session.add_all(runs)
        session.commit()
        ids = [run.id for run in runs]

    cj = {s["key"]: s for s in admin.get("/v1/admin/sources").json()}["cj"]
    assert (cj["last_run"]["id"], cj["last_run"]["blocked_by"]) == (ids[2], blocker)
    page = admin.get("/v1/admin/runs", params={"source": "cj"}).json()["items"]
    assert [(r["id"], r["blocked_by"]) for r in page] == [
        (ids[2], blocker),
        (ids[1], None),
        (ids[0], None),
        (blocker, None),
    ]
    assert admin.get(f"/v1/admin/runs/{ids[2]}").json()["blocked_by"] == blocker


@pytest.mark.parametrize("surface", ["runs", "targets", "gaps"])
@pytest.mark.parametrize("limit", [1, 50, 200])
def test_collection_traversal(admin: TestClient, engine: Engine, surface: str, limit: int) -> None:
    run_id = record(engine, 2, NOW)
    with Session(engine) as session:
        if surface == "runs":
            session.add_all(
                CollectorRun(source_id=2, trigger="csv", queued_at=NOW) for _ in range(240)
            )
        elif surface == "targets":
            session.add_all(
                CollectorRunTarget(
                    run_id=run_id,
                    scope=f"scope-{i // 120}",
                    target_id=f"target:{i % 120:03}",
                    captured_at=NOW,
                )
                for i in range(241)
            )
        else:
            session.add_all(
                CollectionGap(
                    source_id=2 if i < 240 else 3,
                    slot_key=f"fixture-{i:03}",
                    slot_start=NOW - timedelta(minutes=i // 120),
                    slot_end=NOW + timedelta(hours=1),
                    reason="host_offline",
                )
                for i in range(241)
            )
        session.commit()
        if surface == "runs":
            path, field = "/v1/admin/runs", "items"
            expected: list[Any] = list(
                session.scalars(select(CollectorRun.id).order_by(CollectorRun.id.desc()))
            )
        elif surface == "targets":
            path, field = f"/v1/admin/runs/{run_id}", "targets"
            expected = [(f"scope-{i // 120}", f"target:{i % 120:03}") for i in range(241)]
        else:
            path, field = "/v1/admin/host", "open_gaps"
            expected = [f"fixture-{i:03}" for i in sorted(range(241), key=lambda i: (i // 120, -i))]
    first = admin.get(path).json()
    assert len(first[field]) == 50 and first["next_cursor"] is not None
    if surface == "gaps":
        assert all(g["source_key"] == "cj" for g in first[field])
        assert set(first["latest_gap_ends"]) == {"cj", "google_trends"}
    seen: list[Any] = []
    params: dict[str, Any] = {"limit": limit}
    for _ in range(242):
        response = admin.get(path, params=params)
        assert response.status_code == 200
        page = response.json()
        assert 0 < len(page[field]) <= limit
        seen.extend(
            row["id"]
            if surface == "runs"
            else (row["scope"], row["target_id"])
            if surface == "targets"
            else row["slot_key"]
            for row in page[field]
        )
        if page["next_cursor"] is None:
            break
        params["cursor"] = page["next_cursor"]
    else:
        pytest.fail("cursor did not terminate")
    assert seen == expected
    assert len(set(seen)) == 241


@pytest.mark.parametrize("path", ["/v1/admin/runs", "/v1/admin/runs/1", "/v1/admin/host"])
@pytest.mark.parametrize(
    "query",
    [{"limit": 0}, {"limit": 201}, {"cursor": ""}, {"cursor": "{}"}, {"cursor": "[true,0]"}],
)
def test_collection_rejects_invalid_paging(
    admin: TestClient, engine: Engine, path: str, query: dict[str, Any]
) -> None:
    run_id = record(engine, 2, NOW)
    response = admin.get(path.replace("/runs/1", f"/runs/{run_id}"), params=query)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "live,worktree,enabled,status,code",
    [
        (False, False, True, 409, "collectors_live_off"),
        (True, True, True, 409, "collectors_live_off"),
        (True, False, False, 409, "source_disabled"),
        (True, False, True, 202, None),
    ],
)
def test_run_now_needs_live_collectors(
    admin: TestClient,
    engine: Engine,
    settings: Settings,
    live: bool,
    worktree: bool,
    enabled: bool,
    status: int,
    code: str | None,
) -> None:
    published: list[int] = []
    assert isinstance(admin.app, FastAPI)
    live_settings = settings.model_copy(update={"collectors_live": live})
    admin.app.dependency_overrides[get_settings] = lambda: live_settings
    admin.app.dependency_overrides[get_publisher] = lambda: published.append
    with Session(engine) as session:
        session.execute(update(Source).where(Source.key == "cj").values(enabled=enabled))
        session.commit()
    with patch("pulso_api.routers.admin.is_linked_worktree", return_value=worktree):
        response = admin.post("/v1/admin/sources/cj/run")
    assert response.status_code == status
    with Session(engine) as session:
        runs = session.scalars(select(CollectorRun)).all()
    if code:
        assert response.json()["code"] == code
        assert (runs, published) == ([], [])
    else:
        assert response.json()["status"] == "queued"
        assert response.json()["started_at"] is None
        assert published == [runs[0].id] == [response.json()["id"]]
        assert runs[0].trigger == "manual"


def test_patch_toggles_and_appends_one_event(admin: TestClient, engine: Engine) -> None:
    response = admin.patch("/v1/admin/sources/cj", json={"enabled": False, "reason": " paused "})
    assert response.status_code == 200
    body = response.json()
    assert (body["enabled"], body["status"], body["disabled_reason"]) == (
        False,
        "disabled",
        "paused",
    )
    with Session(engine) as session:
        session.execute(update(Source).where(Source.key == "cj").values(status="blocked"))
        session.commit()
    again = admin.patch("/v1/admin/sources/cj", json={"enabled": False})
    assert again.json()["status"] == "blocked"  # disabling cannot launder a block
    blocked = admin.patch("/v1/admin/sources/cj", json={"enabled": True})
    assert blocked.json()["code"] == "reason_required"
    extra = admin.patch("/v1/admin/sources/cj", json={"enabled": True, "config": {}})
    assert extra.status_code == 422
    enabled = admin.patch("/v1/admin/sources/cj", json={"enabled": True, "reason": "unblocked"})
    assert (enabled.json()["status"], enabled.json()["disabled_at"]) == ("active", None)
    with Session(engine) as session:
        events = session.scalars(select(SourceEvent).order_by(SourceEvent.id)).all()
    assert [(e.actor, e.action, e.reason) for e in events] == [
        (str(PRINCIPAL.user_id), "disable", "paused"),
        (str(PRINCIPAL.user_id), "disable", None),
        (str(PRINCIPAL.user_id), "enable", "unblocked"),
    ]
    assert admin.patch("/v1/admin/sources/nope", json={"enabled": True}).status_code == 404


def test_disable_keeps_a_block_committed_after_the_lookup(
    admin: TestClient, engine: Engine, settings: Settings
) -> None:
    """R1: a framework block landing between the route's lookup and its write survives."""
    with Session(engine) as session:
        session.execute(
            update(Source)
            .where(Source.key == "cj")
            .values(enabled=True, status="active", consecutive_block_count=4)
        )
        run_id = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None).id

    def block_after_lookup(session: Session, key: str) -> Source:
        source = get_source(session, key)
        with (
            Session(engine) as runner,
            patch("pulso_sources.framework.lifecycle.fetch", return_value=Response(None, 429)),
        ):
            target = Target("catalog", "fixture", [Request()])
            execute_run(runner, run_id, Mock(), [target], settings=settings)
        return source

    with patch("pulso_api.routers.admin.get_source", side_effect=block_after_lookup):
        disabled = admin.patch("/v1/admin/sources/cj", json={"enabled": False})
    assert (disabled.json()["status"], disabled.json()["disabled_reason"]) == (
        "blocked",
        "consecutive_blocks:http_429",
    )
    with Session(engine) as session:
        assert session.get_one(Source, 2).consecutive_block_count == 5
    enabled = admin.patch("/v1/admin/sources/cj", json={"enabled": True})
    assert (enabled.status_code, enabled.json()["code"]) == (422, "reason_required")


@pytest.mark.parametrize("engine", [pytest.param("postgres", marks=pytest.mark.db)], indirect=True)
def test_toggle_waits_for_a_concurrent_block(admin: TestClient, engine: Engine) -> None:
    """R1: the row lock makes a disable decide on a block committed while it waited."""

    def lock_waits() -> bool:
        with engine.connect() as connection:  # fresh snapshot of pg_stat_activity per poll
            return bool(
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_stat_activity"
                        " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            )

    with Session(engine) as session:  # a running source, so a stale write would change status
        session.execute(
            update(Source).where(Source.key == "cj").values(enabled=True, status="active")
        )
        session.commit()
    # Closing the framework session first releases its lock before the pool joins.
    with ThreadPoolExecutor(1) as pool, Session(engine) as framework:
        framework.execute(
            update(Source)
            .where(Source.key == "cj")
            .values(enabled=False, status="blocked", disabled_reason="consecutive_blocks:http_429")
        )
        pending = pool.submit(admin.patch, "/v1/admin/sources/cj", json={"enabled": False})
        deadline = time.monotonic() + 10
        while not lock_waits():
            assert time.monotonic() < deadline, "the toggle never waited on the source row"
            time.sleep(0.05)
        framework.commit()
        disabled = pending.result(timeout=10)
    assert (disabled.json()["status"], disabled.json()["disabled_reason"]) == (
        "blocked",
        "consecutive_blocks:http_429",
    )
    enabled = admin.patch("/v1/admin/sources/cj", json={"enabled": True})
    assert (enabled.status_code, enabled.json()["code"]) == (422, "reason_required")


def test_publish_failure_logs_only_the_error_class(
    admin: TestClient, engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """I1: broker errors can carry credentials; the API log keeps only the class name."""
    marker = "fixture-only-broker-credential-marker"

    def failing_publish(run_id: int) -> None:
        raise ConnectionError(marker)

    assert isinstance(admin.app, FastAPI)
    live_settings = settings.model_copy(update={"collectors_live": True})
    admin.app.dependency_overrides[get_settings] = lambda: live_settings
    admin.app.dependency_overrides[get_publisher] = lambda: failing_publish
    with Session(engine) as session:
        session.execute(update(Source).where(Source.key == "cj").values(enabled=True))
        session.commit()
    output = io.StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonFormatter())
    monkeypatch.setattr(logging.getLogger("pulso"), "handlers", [handler])
    with patch("pulso_api.routers.admin.is_linked_worktree", return_value=False):
        response = admin.post("/v1/admin/sources/cj/run")
    assert (response.status_code, response.json()["code"]) == (500, "internal_error")
    with Session(engine) as session:
        run = session.scalars(select(CollectorRun)).one()
    assert (run.status, run.error_code) == ("failed", "publish_failed")
    assert "ConnectionError" in output.getvalue()
    assert marker not in output.getvalue() + response.text


def test_coverage_excludes_internal_sources(admin: TestClient, engine: Engine) -> None:
    old = NOW - timedelta(days=30)
    for source_id in (2, 5):
        record(engine, source_id, NOW, a="success")
        record(engine, source_id, old, a="success")
        record(engine, source_id, NOW + timedelta(days=400), a="success")
    if engine.dialect.name == "sqlite":  # mirror what the Postgres view derives from evidence
        with engine.begin() as connection:
            connection.execute(
                insert(Table("source_daily_coverage", MetaData(), autoload_with=connection)),
                [
                    dict(source_id=s, day=d.date(), status="success", runs=1, rows=0, targets=1)
                    | {"successful_targets": 1}
                    for s in (2, 5)
                    for d in (NOW, old, NOW + timedelta(days=400))
                ],
            )
    days = admin.get("/v1/admin/coverage", params={"days": 7}).json()
    assert days == [
        {
            "source_key": "cj",
            "day": NOW.date().isoformat(),
            "status": "success",
            "runs": 1,
            "rows": 0,
            "targets": 1,
            "successful_targets": 1,
        }
    ]
    assert admin.get("/v1/admin/coverage", params={"days": 0}).status_code == 422


def test_host_reports_latest_heartbeat_and_open_gaps(admin: TestClient, engine: Engine) -> None:
    assert admin.get("/v1/admin/host").json() == {
        "live_runs_allowed": False,
        "latest_heartbeat": None,
        "open_gaps": [],
        "next_cursor": None,
        "latest_gap_ends": {},
    }
    run = record(engine, 2, NOW, a="success")
    with Session(engine) as session:
        session.add_all(
            [
                HostHeartbeat(host="pc", at=NOW - timedelta(minutes=5)),
                HostHeartbeat(host="pc", at=NOW - timedelta(hours=3)),
                HostHeartbeat(host="other-pc", at=NOW - timedelta(minutes=1)),
            ]
        )
        for source_id, slot, start, filled in [
            (2, "catalog:open", NOW - timedelta(days=1), None),
            (1, "catalog:newer", NOW - timedelta(hours=1), None),
            (2, "catalog:filled", NOW - timedelta(days=2), run),
            (2, "catalog:ancient", NOW - timedelta(days=120), None),
        ]:
            session.add(
                CollectionGap(
                    source_id=source_id,
                    slot_key=slot,
                    slot_start=start,
                    slot_end=start + timedelta(days=1),
                    reason="host_offline",
                    filled_by_run_id=filled,
                )
            )
        session.commit()
    host = admin.get("/v1/admin/host").json()
    assert host["latest_heartbeat"]["host"] == "other-pc"
    assert naive(host["latest_heartbeat"]["at"]) == (NOW - timedelta(minutes=1)).replace(
        tzinfo=None
    )
    assert [(g["source_key"], g["slot_key"]) for g in host["open_gaps"]] == [
        ("shopify_stores", "catalog:newer"),
        ("cj", "catalog:open"),
    ]
    assert naive(host["latest_gap_ends"]["cj"]) == NOW.replace(tzinfo=None)


class ImportAdapter:
    """Accepts the validated rows and writes no observations (the source packages own those)."""

    parser_version = "1"

    def __init__(self, data: ImportData) -> None:
        self.data = data

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise AssertionError("imports never fetch")

    def parse(self, body: bytes) -> list[Row]:
        if self.data.csv is None:
            assert json.loads(body) == {"products": []}
            return []
        return self.data.csv.rows

    def upsert(
        self, session: Session, records: Sequence[Row], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        return UpsertStats(inserted=len(records))


def test_import_template_and_preview_write_nothing(admin: TestClient, engine: Engine) -> None:
    template = admin.get("/v1/admin/sources/google_trends/import/template")
    assert template.headers["content-type"].startswith("text/csv")
    assert template.content == template_csv("google_trends")
    assert admin.get("/v1/admin/sources/backup/import/template").status_code == 404
    keys = {s["key"]: s["csv_import"] for s in admin.get("/v1/admin/sources").json()}
    assert keys == {
        "shopify_stores": "preview_only",
        "cj": "preview_only",
        "google_trends": "ready",
        "fx_frankfurter": "ready",
        "backup": None,
    }

    def preview(key: str, body: bytes) -> dict[str, Any]:
        response = admin.post(
            f"/v1/admin/sources/{key}/import/preview",
            content=body,
            headers={"Content-Type": "application/octet-stream"},
        )
        result: dict[str, Any] = response.json()
        return result

    body = template.content + b"other,2026-13-01,50,US,manual\n\n"
    checked = preview("google_trends", body)
    assert {k: checked[k] for k in ("valid", "invalid", "skipped", "error_count")} == {
        "valid": 1,
        "invalid": 1,
        "skipped": 1,
        "error_count": 1,
    }
    assert checked["errors"] == [{"row": 3, "column": "date", "message": "Invalid date value"}]
    assert checked["rows"][0]["keyword"] == "example keyword"

    many = template_csv("google_trends") + b"k,bad,50,US,x\n" * 150
    capped = preview("google_trends", many)
    assert (len(capped["errors"]), capped["error_count"], capped["invalid"]) == (100, 150, 150)
    twice = template_csv("cj") + template_csv("cj").splitlines(keepends=True)[1]
    duplicate = preview("cj", twice)  # rejects the whole file, naming both rows
    assert (duplicate["valid"], duplicate["invalid"]) == (0, 2)
    assert preview("cj", b"nope\n1\n")["code"] == "invalid_file"
    assert preview("cj", b"name\xff\n")["detail"] == "Save the file as CSV UTF-8."
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CollectorRun)) == 0
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 0


def test_import_commit_then_repeat_skips(
    admin: TestClient, engine: Engine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    objects: dict[str, bytes] = {}
    s3 = Mock()
    s3.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: s3)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setitem(ADAPTERS, "google_trends", ImportAdapter)
    upload = {"headers": {"Content-Type": "application/octet-stream"}}
    body = template_csv("google_trends") + b"other,2026-13-01,50,US,manual\n"

    first = admin.post("/v1/admin/sources/google_trends/import", content=body, **upload).json()
    assert (first["run"]["status"], first["run"]["trigger"]) == ("success", "csv")
    assert first["run"]["rows_inserted"] == 1 and first["original_run_id"] is None
    assert first["error_count"] == 1 and first["errors"][0]["row"] == 3
    repeat = admin.post("/v1/admin/sources/google_trends/import", content=body, **upload).json()
    assert (repeat["run"]["status"], repeat["in_progress"]) == ("skipped", False)
    assert (repeat["raw_payload_id"], repeat["original_run_id"]) == (
        first["raw_payload_id"],
        first["run"]["id"],
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    assert s3.put_object.call_count == 1

    json_cj = admin.post(
        "/v1/admin/sources/cj/import", params={"mode": "json"}, content=b"{}", **upload
    )
    assert json_cj.json()["code"] == "invalid_import"
    unbuilt = admin.post("/v1/admin/sources/cj/import", content=template_csv("cj"), **upload)
    assert (unbuilt.status_code, unbuilt.json()["code"]) == (409, "import_unavailable")


IMPORT_PATHS = [
    "/v1/admin/sources/google_trends/import/preview",
    "/v1/admin/sources/google_trends/import",
    "/v1/admin/sources/shopify_stores/import?mode=json&observed_for=2026-10-22",
]


def stream_upload(
    client: TestClient, path: str, chunks: list[bytes], headers: dict[str, str]
) -> tuple[httpx.Response, int]:
    """ASGITransport preserves chunk boundaries; TestClient joins the request stream."""
    received = 0

    async def body() -> AsyncIterator[bytes]:
        nonlocal received
        for chunk in chunks:
            received += len(chunk)
            yield chunk

    async def send() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=client.app), base_url="http://testserver"
        ) as transport:
            request = transport.build_request(
                "POST", path, content=body(), headers={"Content-Type": "application/octet-stream"}
            )
            del request.headers["Transfer-Encoding"]  # distinguish missing length from chunked
            request.headers.update(headers)
            return await transport.send(request)

    return asyncio.run(send()), received


@pytest.mark.parametrize("path", IMPORT_PATHS)
@pytest.mark.parametrize(
    "headers,expected_received",
    [
        ({"Content-Length": str(MAX_BYTES + 1)}, 0),
        ({}, MAX_BYTES + 1),
        ({"Transfer-Encoding": "chunked"}, MAX_BYTES + 1),
        ({"Content-Length": str(MAX_BYTES)}, MAX_BYTES + 1),
        ({"Content-Length": "0"}, MAX_BYTES + 1),
        ({"Content-Length": "invalid"}, MAX_BYTES + 1),
    ],
)
def test_oversized_import_stops_before_tail_and_writes_nothing(
    admin: TestClient, engine: Engine, path: str, headers: dict[str, str], expected_received: int
) -> None:
    with (
        patch("pulso_api.routers.admin.parse_csv") as parse,
        patch("pulso_api.routers.admin.commit_import") as commit,
        patch.object(storage, "make_client") as s3,
    ):
        response, received = stream_upload(
            admin, path, [b"x" * MAX_BYTES, b"x", b"unread tail"], headers
        )
    assert received == expected_received
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "about:blank",
        "title": "Unprocessable Content",
        "status": 422,
        "code": "invalid_file",
        "detail": "File exceeds 20 MiB",
        "request_id": response.headers["x-request-id"],
        "errors": [],
    }
    parse.assert_not_called()
    commit.assert_not_called()
    s3.assert_not_called()
    with Session(engine) as session:
        for model in (CollectorRun, RawPayload, CollectorRunTarget):
            assert session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("path", IMPORT_PATHS)
@pytest.mark.parametrize("declared", [False, True])
def test_exact_import_cap_accepts_original_bytes(
    admin: TestClient,
    engine: Engine,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    declared: bool,
) -> None:
    objects: dict[str, bytes] = {}
    s3 = Mock()
    s3.put_object.side_effect = lambda **kw: objects.__setitem__(kw["Key"], kw["Body"])
    s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: s3)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    for key in ("google_trends", "shopify_stores"):
        monkeypatch.setitem(ADAPTERS, key, ImportAdapter)
    if "mode=json" in path:
        body = b'{"products": []}'.ljust(MAX_BYTES)
    else:
        template = template_csv("google_trends")
        body = template.replace(
            b"keyword,", b"keyword" + b" " * (MAX_BYTES - len(template)) + b",", 1
        )
    assert len(body) == MAX_BYTES
    headers = {"Content-Length": str(MAX_BYTES)} if declared else {}
    response, received = stream_upload(admin, path, [body[:-1], body[-1:]], headers)
    assert (response.status_code, received) == (200, MAX_BYTES)
    if path.endswith("preview"):
        assert response.json()["valid"] == 1
        s3.put_object.assert_not_called()
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(CollectorRun)) == 0
    else:
        first = response.json()
        assert first["run"]["status"] == "success"
        assert [gzip.decompress(value) for value in objects.values()] == [body]
        repeat, received = stream_upload(admin, path, [body], headers)
        assert (repeat.status_code, received) == (200, MAX_BYTES)
        assert repeat.json()["run"]["status"] == "skipped"
        assert repeat.json()["original_run_id"] == first["run"]["id"]
        assert s3.put_object.call_count == 1


@pytest.mark.parametrize("path", IMPORT_PATHS)
def test_oversized_import_non_admin_is_403_without_reading_body(
    client: TestClient, signed_token: Callable[[dict[str, Any]], str], path: str
) -> None:
    token = signed_token({"sub": "user_other"})
    response, received = stream_upload(
        client,
        path,
        [b"unread"],
        {"Authorization": "Bearer " + token, "Content-Length": str(MAX_BYTES + 1)},
    )
    assert received == 0
    assert (response.status_code, response.json()["code"]) == (403, "not_allowlisted")


@pytest.mark.parametrize("path", IMPORT_PATHS)
def test_import_body_is_required(admin: TestClient, path: str) -> None:
    response = admin.post(path, content=b"", headers={"Content-Type": "application/octet-stream"})
    assert (response.status_code, response.json()["code"]) == (422, "validation_error")
    assert response.json()["errors"] == [
        {"loc": ["body"], "msg": "Field required", "type": "missing"}
    ]
