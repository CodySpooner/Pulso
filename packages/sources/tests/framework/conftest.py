from pathlib import Path

import pytest

from pulso_core.settings import Settings


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://fixture@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "fixture")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "fixture")
    return Settings()
