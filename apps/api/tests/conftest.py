import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.orm import Session

from pulso_api.auth import jwks_client
from pulso_api.dependencies import get_db
from pulso_api.main import create_app
from pulso_core.settings import Settings, get_settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    for name, value in {
        "DATABASE_URL": "postgresql+psycopg://localhost/pulso_test",
        "S3_ACCESS_KEY_ID": "fixture",
        "S3_SECRET_ACCESS_KEY": "fixture",
        "CLERK_ISSUER": "https://clerk.example.test",
        "CLERK_JWKS_URL": "https://clerk.example.test/.well-known/jwks.json",
        "CLERK_AUTHORIZED_PARTIES": "https://pulso.example.test",
        "PLATFORM_ADMIN_USER_IDS": "user_a,user_b",
    }.items():
        monkeypatch.setenv(name, value)
    return Settings()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    def no_database() -> Iterator[Session]:
        with Session() as session:
            yield session

    app.dependency_overrides[get_db] = no_database
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def signed_token() -> Iterator[Callable[[dict[str, Any]], str]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    public_key.update({"kid": "fixture-key", "use": "sig", "alg": "RS256"})
    jwks_client.cache_clear()

    def sign(overrides: dict[str, Any]) -> str:
        now = int(datetime.now(UTC).timestamp())
        claims: dict[str, Any] = {
            "iss": "https://clerk.example.test",
            "sub": "user_a",
            "iat": now,
            "nbf": now - 1,
            "exp": now + 60,
            "azp": "https://pulso.example.test",
        }
        claims.update(overrides)
        claims = {key: value for key, value in claims.items() if value is not None}
        return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "fixture-key"})

    with patch("jwt.PyJWKClient.fetch_data", return_value={"keys": [public_key]}):
        yield sign
    jwks_client.cache_clear()
