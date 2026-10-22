from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

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
from pulso_api.routers.admin import get_publisher
from pulso_core.db import Base
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

    detail = admin.get(f"/v1/admin/runs/{first}").json()
    assert [(t["target_id"], t["status"]) for t in detail["targets"]] == [
        ("a", "success"),
        ("b", "success"),
    ]
    assert all(isinstance(t["raw_payload_id"], int) for t in detail["targets"])
    assert admin.get("/v1/admin/runs/999").status_code == 404


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


def test_coverage_excludes_internal_sources(admin: TestClient, engine: Engine) -> None:
    old = NOW - timedelta(days=30)
    for source_id in (2, 5):
        record(engine, source_id, NOW, a="success")
        record(engine, source_id, old, a="success")
    if engine.dialect.name == "sqlite":  # mirror what the Postgres view derives from evidence
        with engine.begin() as connection:
            connection.execute(
                insert(Table("source_daily_coverage", MetaData(), autoload_with=connection)),
                [
                    dict(source_id=s, day=d.date(), status="success", runs=1, rows=0, targets=1)
                    | {"successful_targets": 1}
                    for s in (2, 5)
                    for d in (NOW, old)
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
    }
    run = record(engine, 2, NOW, a="success")
    with Session(engine) as session:
        session.add_all(
            [
                HostHeartbeat(host="pc", at=NOW - timedelta(minutes=5)),
                HostHeartbeat(host="pc", at=NOW - timedelta(hours=3)),
            ]
        )
        for slot, start, filled in [
            ("catalog:open", NOW - timedelta(days=1), None),
            ("catalog:filled", NOW - timedelta(days=2), run),
            ("catalog:ancient", NOW - timedelta(days=120), None),
        ]:
            session.add(
                CollectionGap(
                    source_id=2,
                    slot_key=slot,
                    slot_start=start,
                    slot_end=start + timedelta(days=1),
                    reason="host_offline",
                    filled_by_run_id=filled,
                )
            )
        session.commit()
    host = admin.get("/v1/admin/host").json()
    assert naive(host["latest_heartbeat"]["at"]) == (NOW - timedelta(minutes=5)).replace(
        tzinfo=None
    )
    assert [(g["source_key"], g["slot_key"]) for g in host["open_gaps"]] == [("cj", "catalog:open")]
