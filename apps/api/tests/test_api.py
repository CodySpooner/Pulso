import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.main import create_app
from pulso_api.openapi import export
from pulso_api.routers.health import check_postgres
from pulso_core import db
from pulso_core.logging import JsonFormatter, request_id
from pulso_core.settings import Settings


def test_health_without_settings_or_services() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz", headers={"X-Request-ID": "fixture-request"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "fixture-request"


def test_api_engines_have_statement_timeout() -> None:
    db._process_engine.cache_clear()
    settings = Settings(
        database_url="postgresql+psycopg://localhost/pulso_test",
        s3_access_key_id="fixture",
        s3_secret_access_key="fixture",
        _env_file=None,
    )
    try:
        with (
            patch.object(db, "get_settings", return_value=settings),
            patch.object(db, "create_engine") as create,
        ):
            dependency = get_db()
            session = next(dependency)
            assert session.get_bind() is create.return_value
            with pytest.raises(StopIteration):
                next(dependency)
            check_postgres(settings)
            create.assert_called_once()
            assert create.call_args.kwargs["connect_args"]["options"] == (
                "-c timezone=UTC -c statement_timeout=10000"
            )
    finally:
        db._process_engine.cache_clear()


def test_readiness_names_redis_and_redacts_details(client: TestClient) -> None:
    with (
        patch("pulso_api.routers.health.check_postgres"),
        patch("pulso_api.routers.health.check_s3"),
        patch("pulso_api.routers.health.check_redis", side_effect=ConnectionError("secret-url")),
    ):
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["detail"] == "Unavailable dependencies: redis"
    assert "secret-url" not in response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    "claims,code",
    [
        ({"iss": "https://other.example.test"}, "bad_token"),
        ({"exp": 1}, "bad_token"),
        ({"nbf": 9999999999}, "bad_token"),
        ({"azp": "https://attacker.example.test"}, "bad_azp"),
        ({"azp": None}, "bad_token"),
        ({"sub": None}, "bad_token"),
        ({"nbf": None}, "bad_token"),
    ],
)
def test_invalid_jwt_rejected(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
    claims: dict[str, Any],
    code: str,
) -> None:
    with patch("pulso_api.auth.provision_principal") as provision:
        response = client.get("/v1/me", headers={"Authorization": "Bearer " + signed_token(claims)})
    assert response.status_code == 401
    assert response.json()["code"] == code
    provision.assert_not_called()


def test_non_allowlisted_subject_gets_no_rows(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
) -> None:
    with patch("pulso_api.auth.provision_principal") as provision:
        response = client.get(
            "/v1/me",
            headers={
                "Authorization": "Bearer " + signed_token({"sub": "user_other"}),
            },
        )
    assert response.status_code == 403
    assert response.json()["code"] == "not_allowlisted"
    provision.assert_not_called()


def test_wrong_algorithm_rejected(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
) -> None:
    token = jwt.encode(
        {"sub": "user_a"}, "fixture-secret" * 4, algorithm="HS256", headers={"kid": "fixture-key"}
    )
    assert client.get("/v1/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_valid_bearer_and_cookie(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
) -> None:
    principal = Principal(uuid4(), uuid4())
    token = signed_token({})
    with patch("pulso_api.auth.provision_principal", return_value=principal):
        response = client.get("/v1/me", headers={"Authorization": "Bearer " + token})
        assert response.json() == {
            "user_id": str(principal.user_id),
            "workspace_id": str(principal.workspace_id),
            "is_admin": True,
        }
        client.cookies.set("__session", token)
        assert client.get("/v1/me").status_code == 200
        assert client.get("/v1/me", headers={"Authorization": "Bearer broken"}).status_code == 401


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/v1/me", 401, "missing_token"),
        ("/missing", 404, "not_found"),
    ],
)
def test_problem_shape(client: TestClient, path: str, status: int, code: str) -> None:
    response = client.get(path)
    assert response.status_code == status
    assert response.json()["code"] == code
    assert set(response.json()) == {
        "type",
        "title",
        "status",
        "code",
        "detail",
        "request_id",
        "errors",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"workspace_id": str(uuid4())},
        {"payment_fee_bps": 10001},
        {"default_cpa_minor": -1},
        {"default_cpa_minor": 1.5},
        {"default_cpa_minor": True},
        {"currency": "EUR"},
        {"target_margin_bps": None},
        {"default_cpa_minor": 2**63},
    ],
)
def test_settings_boundary_rejects_invalid_values(
    client: TestClient, payload: dict[str, Any]
) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    response = client.patch("/v1/settings", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["errors"]


def test_openapi_export_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    export(first)
    export(second)
    assert first.read_bytes() == second.read_bytes()
    schema = json.loads(first.read_bytes())
    operations = [op for path in schema["paths"].values() for op in path.values()]
    assert len({op["operationId"] for op in operations}) == len(operations) == 5
    assert all(
        "schema" in op["responses"]["200"]["content"]["application/json"] for op in operations
    )
    assert schema["paths"]["/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]


def test_logging_correlation_and_request_id_validation(client: TestClient) -> None:
    token = request_id.set("fixture-id")
    try:
        record = logging.LogRecord("pulso.api", logging.INFO, "", 0, "request", (), None)
        assert json.loads(JsonFormatter().format(record))["request_id"] == "fixture-id"
    finally:
        request_id.reset(token)
    response = client.get("/healthz", headers={"X-Request-ID": "x" * 129})
    assert len(response.headers["X-Request-ID"]) == 36
