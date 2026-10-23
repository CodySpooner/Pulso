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


def test_collector_defaults_and_honest_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    set_required(monkeypatch)
    s = Settings()
    assert (s.collector_block_threshold, s.collector_max_retries) == (5, 3)
    assert (s.collect_soft_time_limit_seconds, s.collect_hard_time_limit_seconds) == (3600, 4500)
    assert (s.shopify_requests_per_minute, s.shopify_js_panel_size) == (30, 10)
    assert (s.trends_monthly_search_limit, s.trends_hourly_search_limit) == (250, 50)
    with pytest.raises(ValueError, match="PULSO_BOT_CONTACT"):
        _ = s.collector_user_agent
    # The exact DEC-073 crawler identity.
    monkeypatch.setenv(
        "PULSO_BOT_CONTACT", "https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md"
    )
    monkeypatch.setenv("CJ_API_KEY", "fixture-cj-secret")
    monkeypatch.setenv("SERPAPI_API_KEY", "fixture-serpapi-secret")
    configured = Settings()
    assert configured.collector_user_agent == (
        "PulsoBot/0.1 (+https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md)"
    )
    assert "fixture-cj-secret" not in repr(configured)
    assert "fixture-serpapi-secret" not in repr(configured)


@pytest.mark.parametrize(
    "name,value",
    [
        ("SHOPIFY_REQUESTS_PER_MINUTE", "31"),
        ("TRENDS_MONTHLY_SEARCH_LIMIT", "251"),
        ("TRENDS_HOURLY_SEARCH_LIMIT", "51"),
        ("TRENDS_HOURLY_SEARCH_LIMIT", "0"),
        ("CJ_REQUESTS_PER_SECOND", "2"),
        ("COLLECTOR_BLOCK_THRESHOLD", "0"),
        ("COLLECTOR_RETRY_WAIT_CAP_SECONDS", "601"),
        ("PULSO_BOT_CONTACT", "file:///bot"),
        *(
            (name, "3600")
            for name in (
                "COLLECTOR_WALL_TIME_SECONDS",
                "SHOPIFY_WALL_TIME_SECONDS",
                "CJ_WALL_TIME_SECONDS",
                "TRENDS_WALL_TIME_SECONDS",
                "FX_WALL_TIME_SECONDS",
            )
        ),
        ("COLLECT_SOFT_TIME_LIMIT_SECONDS", "4500"),
        ("COLLECT_HARD_TIME_LIMIT_SECONDS", "3600"),
        ("COLLECTOR_BACKOFF_BASE_SECONDS", "31"),
    ],
)
def test_collector_limits_fail_closed(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    set_required(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()
