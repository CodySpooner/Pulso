from inspect import unwrap
from unittest.mock import MagicMock, patch

import conftest
import pytest


def test_fixture_excludes_public_from_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/pulso_test")
    admin, isolated = MagicMock(), MagicMock()
    with (
        patch.object(conftest, "create_engine", side_effect=[admin, isolated]) as create,
        patch("conftest.command.upgrade"),
    ):
        fixture = unwrap(conftest.db_engine)()
        assert next(fixture) is isolated
        options = create.call_args.kwargs["connect_args"]["options"]
        schema = options.split("search_path=", 1)[1].split()[0]
        assert schema.startswith("test_")
        assert "," not in schema
        assert "public" not in options
        fixture.close()
