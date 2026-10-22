from pathlib import Path

import pytest
from pydantic import ValidationError

from pulso_core.settings import Settings

REQUIRED = {
    "DATABASE_URL": "postgresql+psycopg://pulso:pw@localhost:5432/pulso",
    "S3_ACCESS_KEY_ID": "key",
    "S3_SECRET_ACCESS_KEY": "s3-secret-value",
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run in an empty dir so a developer's .env / .env.local can't leak into the tests.
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def set_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED.items():
        monkeypatch.setenv(name, value)


def test_defaults_keep_scheduler_and_live_collectors_off(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    s = Settings()
    assert s.pulso_scheduler is False
    assert s.collectors_live is False
    assert s.redis_url.get_secret_value() == "redis://localhost:6379/0"
    assert s.s3_bucket_raw == "pulso-raw"
    assert s.api_port == 8000
    assert s.platform_admin_user_ids == []


def test_flags_parse_on(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv("PULSO_SCHEDULER", "on")
    monkeypatch.setenv("COLLECTORS_LIVE", "on")
    s = Settings()
    assert s.pulso_scheduler is True
    assert s.collectors_live is True


def test_comma_separated_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv("PLATFORM_ADMIN_USER_IDS", "user_a, user_b")
    monkeypatch.setenv("CLERK_AUTHORIZED_PARTIES", "http://localhost:3000")
    s = Settings()
    assert s.platform_admin_user_ids == ["user_a", "user_b"]
    assert s.clerk_authorized_parties == ["http://localhost:3000"]


def test_env_local_overrides_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    set_required(monkeypatch)
    monkeypatch.delenv("DATABASE_URL")
    (tmp_path / ".env").write_text("DATABASE_URL=postgresql+psycopg://pulso@localhost/pulso\n")
    (tmp_path / ".env.local").write_text("DATABASE_URL=postgresql+psycopg://pulso@localhost/wt\n")
    assert Settings().database_url.get_secret_value().endswith("/wt")


def test_missing_or_empty_secrets_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "")
    with pytest.raises(ValidationError, match="database_url"):
        Settings()


def test_secrets_not_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    text = repr(Settings())
    assert "s3-secret-value" not in text
    assert ":pw@" not in text
