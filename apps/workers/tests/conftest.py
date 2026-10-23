import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from pulso_core.settings import Settings, get_settings
from pulso_workers import beat


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    monkeypatch.setattr(logging.getLogger("pulso"), "propagate", True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(beat, "__file__", str(tmp_path / "installed" / "beat.py"))
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://test:test@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/15")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
