from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, provision_principal
from pulso_api.dependencies import get_db
from pulso_core.models import User, Workspace, WorkspaceMember, WorkspaceSettings

pytestmark = pytest.mark.db


def test_parallel_first_login_creates_one_workspace(db_engine: Engine) -> None:
    barrier = Barrier(2)

    def login() -> Principal:
        with Session(db_engine) as session:
            barrier.wait(timeout=5)
            return provision_principal(session, "user_a")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: login(), range(2)))
    assert results[0] == results[1]
    with Session(db_engine) as session:
        assert provision_principal(session, "user_a") == results[0]
        for model in (User, Workspace, WorkspaceMember, WorkspaceSettings):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        settings = session.get(WorkspaceSettings, results[0].workspace_id)
        assert settings is not None
        assert (settings.default_country, settings.currency) == ("US", "USD")


def test_two_workspace_settings_isolation(
    db_engine: Engine,
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
) -> None:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    a = {"Authorization": "Bearer " + signed_token({"sub": "user_a"})}
    b = {"Authorization": "Bearer " + signed_token({"sub": "user_b"})}
    a_id = client.get("/v1/me", headers=a).json()["workspace_id"]
    b_id = client.get("/v1/me", headers=b).json()["workspace_id"]
    assert a_id != b_id
    assert (
        client.patch("/v1/settings", headers=a, json={"target_margin_bps": 1234}).status_code == 200
    )
    assert client.get("/v1/settings", headers=b).json()["target_margin_bps"] == 0
    assert client.patch("/v1/settings", headers=b, json={"workspace_id": a_id}).status_code == 422
    response = client.patch(
        "/v1/settings", headers={**b, "X-Workspace-ID": a_id}, json={"target_margin_bps": 4321}
    )
    assert response.json()["workspace_id"] == b_id
    assert (
        client.get("/v1/settings", headers={**b, "X-Workspace-ID": a_id}).json()["workspace_id"]
        == b_id
    )
    assert client.get("/v1/settings", headers=a).json()["target_margin_bps"] == 1234
