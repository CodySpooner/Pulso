import json
from collections.abc import Callable, Iterator
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import SavedScreen, Workspace

# WF-1 part a (DEC-336): saved screens are the workspace's own, validated, versioned definitions.
EARLY = {
    "name": "Early & profitable",
    "filters": {"lifecycle": ["emerging", "rising"], "margin_bps_min": 4000},
    "sort": "margin_bps",
}

As = Callable[[str], TestClient]


def test_screens_require_a_session(client: TestClient) -> None:
    assert client.get("/v1/screens").status_code == 401


@pytest.fixture
def as_(client: TestClient, db_engine: Engine) -> As:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    with Session(db_engine) as session:
        workspaces = {key: Workspace(name=key) for key in ("a", "b")}
        session.add_all(workspaces.values())
        session.commit()
        ids = {key: workspace.id for key, workspace in workspaces.items()}
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database

    def switch(key: str) -> TestClient:
        assert isinstance(client.app, FastAPI)
        principal = Principal(uuid4(), ids[key])
        client.app.dependency_overrides[current_principal] = lambda: principal
        return client

    return switch


@pytest.mark.db
def test_a_screen_saves_reads_lists_and_deletes(as_: As, db_engine: Engine) -> None:
    a = as_("a")
    created = a.post("/v1/screens", json=EARLY)
    assert created.status_code == 201, created.text
    screen = created.json()
    assert (screen["name"], screen["sort"], screen["order"], screen["version"]) == (
        "Early & profitable", "margin_bps", "desc", 1,
    )  # fmt: skip
    assert screen["filters"]["margin_bps_min"] == 4000
    assert screen["filters"]["lifecycle"] == ["emerging", "rising"]
    with Session(db_engine) as session:  # stored without the unset filters
        stored = session.scalars(select(SavedScreen.definition)).one()
        assert stored == {
            "filters": {"lifecycle": ["emerging", "rising"], "margin_bps_min": 4000},
            "sort": "margin_bps",
            "order": "desc",
        }
    assert a.get(f"/v1/screens/{screen['id']}").json() == screen
    # The saved definition runs as is.
    filters = a.get(f"/v1/screens/{screen['id']}").json()["filters"]
    ran = a.get("/v1/screener", params={"filters": json.dumps(filters)})
    assert ran.status_code == 200, ran.text
    assert a.post("/v1/screens", json={**EARLY, "name": " Early & profitable "}).status_code == 409
    for name in ("Margin floor", "Fast US shipping"):
        assert a.post("/v1/screens", json={"name": name}).status_code == 201
    first = a.get("/v1/screens", params={"limit": 2}).json()
    rest = a.get("/v1/screens", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    listed = [item["name"] for item in first["items"] + rest["items"]]
    assert listed == ["Early & profitable", "Fast US shipping", "Margin floor"]
    assert rest["next_cursor"] is None
    assert a.delete(f"/v1/screens/{screen['id']}").status_code == 204
    assert a.get(f"/v1/screens/{screen['id']}").status_code == 404
    assert a.delete(f"/v1/screens/{screen['id']}").status_code == 404


@pytest.mark.db
def test_another_workspaces_screen_is_a_404(as_: As) -> None:
    screen = as_("a").post("/v1/screens", json=EARLY).json()
    b = as_("b")
    assert b.get(f"/v1/screens/{screen['id']}").status_code == 404
    assert b.delete(f"/v1/screens/{screen['id']}").status_code == 404
    assert b.get("/v1/screens").json()["items"] == []
    assert b.post("/v1/screens", json=EARLY).status_code == 201  # names are per workspace
    assert as_("a").get(f"/v1/screens/{screen['id']}").status_code == 200


@pytest.mark.db
@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "x" * 81},
        {"name": "Nul\x00"},
        {"name": "Typo", "filters": {"margin_min": 1}},  # unknown filter
        {"name": "Stage", "filters": {"lifecycle": ["booming"]}},
        {"name": "Sort", "sort": "risk"},
        {"name": "Extra", "columns": []},
    ],
)
def test_a_definition_is_validated(as_: As, body: dict[str, object]) -> None:
    response = as_("a").post("/v1/screens", json=body)
    assert response.status_code == 422, response.text
