from collections.abc import Iterator
from pathlib import Path
from runpy import run_path
from unittest.mock import Mock, patch

import pytest
from alembic.config import Config

from pulso_core import db


@pytest.fixture(autouse=True)
def clear_engines() -> Iterator[None]:
    db._process_engine.cache_clear()
    with patch.object(db, "get_settings") as settings:
        settings.return_value.database_url.get_secret_value.return_value = (
            "postgresql+psycopg://localhost/pulso_test"
        )
        yield
    db._process_engine.cache_clear()


def test_engine_options_and_process_cache() -> None:
    with patch.object(db, "create_engine", side_effect=lambda *a, **k: Mock()) as create:
        default = db.get_engine()
        assert db.get_engine() is default
        assert create.call_args.kwargs == {
            "pool_pre_ping": True,
            "hide_parameters": True,
            "connect_args": {"connect_timeout": 3, "options": "-c timezone=UTC"},
        }
        api = db.get_engine(statement_timeout=10_000)
        assert api is not default
        assert db.get_engine(statement_timeout=10_000) is api
        assert create.call_args.kwargs["connect_args"]["options"] == (
            "-c timezone=UTC -c statement_timeout=10000"
        )
        with patch("pulso_core.db.os.getpid", return_value=-1):
            assert db.get_engine() is not default
        assert create.call_count == 3


def test_migration_engine_has_no_statement_timeout() -> None:
    with (
        patch.object(db, "create_engine") as create,
        patch("alembic.context.config", Config(), create=True),
        patch("alembic.context.is_offline_mode", return_value=False),
        patch("alembic.context.configure"),
        patch("alembic.context.begin_transaction"),
        patch("alembic.context.run_migrations"),
    ):
        run_path(str(Path(db.__file__).parent / "migrations/env.py"))
    assert create.call_args.kwargs["connect_args"]["options"] == "-c timezone=UTC"
