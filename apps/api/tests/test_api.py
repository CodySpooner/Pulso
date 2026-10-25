import io
import json
import logging
import socket
import ssl
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4

import jwt
import pytest
from botocore.stub import Stubber
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from pulso_api.__main__ import main
from pulso_api.auth import Principal, current_principal, jwks_client, verify_token
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.main import create_app
from pulso_api.openapi import export
from pulso_api.routers.health import check_postgres
from pulso_core import db
from pulso_core.logging import JsonFormatter, request_id
from pulso_core.s3 import make_client
from pulso_core.settings import Settings


def test_health_without_settings_or_services() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/healthz", headers={"X-Request-ID": "fixture-request"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "fixture-request"


@pytest.mark.parametrize("port", [None, "9080"])
def test_api_bind_address_and_port(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, port: str | None
) -> None:
    monkeypatch.delenv("PORT", raising=False)
    if port is not None:
        monkeypatch.setenv("PORT", port)
    with (
        patch("pulso_api.__main__.get_settings", return_value=settings),
        patch("pulso_api.__main__.uvicorn.Config") as config,
        patch("pulso_api.__main__.uvicorn.Server") as server,
        patch("pulso_api.__main__.socket.create_server") as create,
    ):
        main()
    config.assert_called_once_with(
        "pulso_api.main:app",
        host="::",
        port=int(port) if port is not None else settings.api_port,
        access_log=False,
    )
    create.assert_called_once_with(
        ("::", int(port) if port is not None else settings.api_port),
        family=socket.AF_INET6,
        dualstack_ipv6=True,
    )
    server.assert_called_once_with(config.return_value)
    server.return_value.run.assert_called_once_with(
        sockets=[create.return_value.__enter__.return_value]
    )


@pytest.mark.skipif(not socket.has_dualstack_ipv6(), reason="OS has no dual-stack IPv6")
def test_api_listener_accepts_ipv4_and_ipv6(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setenv("PORT", "0")

    def connect_both(*, sockets: list[socket.socket]) -> None:
        listener = sockets[0]
        listener.settimeout(1)
        port = listener.getsockname()[1]
        for host in ("127.0.0.1", "::1"):
            with socket.create_connection((host, port), timeout=1):
                connection, _ = listener.accept()
                connection.close()

    with (
        patch("pulso_api.__main__.get_settings", return_value=settings),
        patch("pulso_api.__main__.uvicorn.Server.run", side_effect=connect_both) as run,
    ):
        main()
    run.assert_called_once()


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


@pytest.mark.parametrize("available", [True, False])
def test_readiness_checks_s3_and_closes_client(
    client: TestClient, settings: Settings, available: bool
) -> None:
    s3 = make_client(settings)
    with (
        Stubber(s3) as stub,
        patch("pulso_api.routers.health.make_client", return_value=s3) as make_s3,
        patch("pulso_api.routers.health.check_postgres"),
        patch("pulso_api.routers.health.check_redis"),
        patch.object(s3, "close", wraps=s3.close) as close,
    ):
        params = {"Bucket": settings.s3_bucket_raw}
        if available:
            stub.add_response("head_bucket", {}, params)
        else:
            stub.add_client_error("head_bucket", "NoSuchBucket", expected_params=params)
        response = client.get("/readyz")
        config = make_s3.call_args.kwargs["config"]
        assert config.connect_timeout == config.read_timeout == 2
        assert config.retries == {"max_attempts": 1}
        assert response.status_code == (200 if available else 503)
        if not available:
            assert response.json()["detail"] == "Unavailable dependencies: s3"
        stub.assert_no_pending_responses()
        close.assert_called_once_with()


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
        ({"exp": None}, "bad_token"),
        ({"iat": None}, "bad_token"),
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


def test_unknown_kid_rejected(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {"sub": "user_a"}, other_key, algorithm="RS256", headers={"kid": "other-key"}
    )
    with patch("pulso_api.auth.provision_principal") as provision:
        response = client.get("/v1/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401
    assert response.json()["code"] == "bad_token"
    provision.assert_not_called()


@pytest.mark.parametrize("field", ["clerk_issuer", "clerk_jwks_url"])
def test_unconfigured_auth_is_503(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, settings: Settings, field: str
) -> None:
    monkeypatch.setattr(settings, field, None)
    response = client.get("/v1/me", headers={"Authorization": "Bearer fixture"})
    assert response.status_code == 503
    assert response.json()["code"] == "auth_unconfigured"


class FailingBody(io.BytesIO):
    """A JWKS response whose body read fails after the headers arrived."""

    def __init__(self, error: OSError) -> None:
        super().__init__()
        self.error = error

    def read(self, size: int | None = -1) -> bytes:
        raise self.error


HS256_TOKEN = jwt.encode(
    {"sub": "user_a"}, "fixture-secret" * 4, algorithm="HS256", headers={"kid": "fixture-key"}
)


@pytest.mark.parametrize(
    "jwks,status,code",
    [
        (URLError("fixture outage"), 503, "auth_unavailable"),
        (b"<html>Bad gateway</html>", 503, "auth_unavailable"),
        (b"<html>\xe9</html>", 503, "auth_unavailable"),
        # imp-151 (XR-5): PyJWT wraps only open errors; a reset or TLS error mid-body is bare.
        (FailingBody(ConnectionResetError("fixture reset")), 503, "auth_unavailable"),
        (FailingBody(ssl.SSLError("fixture TLS error")), 503, "auth_unavailable"),
        (b'{"keys": []}', 401, "bad_token"),
    ],
)
def test_jwks_fetch_failures(
    client: TestClient, jwks: bytes | Exception | FailingBody, status: int, code: str
) -> None:
    # The real PyJWKClient.fetch_data runs; only the HTTP opener is replaced (no network).
    def open_jwks(*args: Any, **kwargs: Any) -> io.BytesIO:
        if isinstance(jwks, Exception):
            raise jwks
        return jwks if isinstance(jwks, FailingBody) else io.BytesIO(jwks)

    token = HS256_TOKEN
    jwks_client.cache_clear()
    try:
        with (
            patch("urllib.request.OpenerDirector.open", open_jwks),
            patch("pulso_api.auth.provision_principal") as provision,
        ):
            response = client.get("/v1/me", headers={"Authorization": "Bearer " + token})
    finally:
        jwks_client.cache_clear()
    assert response.status_code == status
    assert response.json()["code"] == code
    provision.assert_not_called()


def test_jwks_outage_answers_queued_requests_from_one_fetch(settings: Settings) -> None:
    """imp-151 (XR-6): PyJWT holds its lock across the fetch, so concurrent requests during an
    outage each waited out a fetch in turn. After a failed fetch they answer 503 for 5 s."""
    fetches: list[float] = []

    def open_jwks(*args: Any, **kwargs: Any) -> io.BytesIO:
        fetches.append(time.monotonic())
        time.sleep(0.2)  # the other requests queue behind this fetch
        raise URLError("fixture outage")

    def status() -> int:
        try:
            verify_token(HS256_TOKEN, settings)
        except APIError as exc:
            return exc.status
        return 200

    assert settings.clerk_jwks_url
    jwks_client.cache_clear()
    try:
        with (
            patch("urllib.request.OpenerDirector.open", open_jwks),
            ThreadPoolExecutor(4) as pool,
        ):
            assert list(pool.map(lambda _: status(), range(4))) == [503] * 4
            assert status() == 503  # back-to-back, still inside the cooldown
            assert len(fetches) == 1
            jwks_client(settings.clerk_jwks_url).retry_at = 0  # the 5 s have passed
            assert status() == 503
            assert len(fetches) == 2
    finally:
        jwks_client.cache_clear()


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
    assert len({op["operationId"] for op in operations}) == len(operations) == 26
    for op in operations:
        success = next(op["responses"][s] for s in ("200", "201", "202") if s in op["responses"])
        assert "schema" in next(iter(success["content"].values()))
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


def test_unhandled_exception_logs_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    app = create_app()

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("fixture failure")

    with TestClient(app) as client:
        response = client.get("/crash", headers={"X-Request-ID": "crash-id"})
    assert response.status_code == 500
    assert "fixture failure" not in response.text
    records = [json.loads(line) for line in capsys.readouterr().err.splitlines()]
    failure = next(record for record in records if record["message"] == "request_failed")
    assert failure["request_id"] == "crash-id"
    assert failure["error_type"] == "RuntimeError"
    assert "Traceback (most recent call last)" in failure["exc_info"]
    assert "in crash" in failure["exc_info"]
    assert "RuntimeError: fixture failure" in failure["exc_info"]
