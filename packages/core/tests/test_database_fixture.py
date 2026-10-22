from inspect import unwrap
from unittest.mock import MagicMock, patch

import conftest
import pytest


def test_fixture_excludes_public_from_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/pulso_test")
    admin, isolated = MagicMock(), MagicMock()
    for engine in (admin, isolated):
        engine.begin.return_value.__enter__.return_value.scalar.return_value = "pulso_test"
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


@pytest.mark.parametrize(
    "suffix",
    [
        "pulso",
        "postgres",
        "",
        "pulso_test?dbname=pulso",
        "pulso_ci?service=collector",
        "pulso_test?host=collector",
        "pulso_test?hostaddr=127.0.0.1",
        "pulso_test?port=5433",
        "pulso_test?user=collector",
        "pulso_test?options=-csearch_path%3Dpublic",
    ],
)
def test_unsafe_test_url_rejected_before_connecting(
    monkeypatch: pytest.MonkeyPatch, suffix: str
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/" + suffix)
    with patch.object(conftest, "create_engine") as create:
        with pytest.raises(pytest.fail.Exception, match="TEST_DATABASE_URL"):
            next(unwrap(conftest.db_engine)())
        create.assert_not_called()


@pytest.mark.parametrize("database", ["pulso_ci", "pulso_test", "pulso_test_isolation"])
def test_allowed_test_database_names(database: str) -> None:
    conftest.require_test_database(database)


@pytest.mark.parametrize("unsafe_connection", [0, 1])
def test_connected_database_checked_before_writes(
    monkeypatch: pytest.MonkeyPatch, unsafe_connection: int
) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+psycopg://localhost/pulso_test")
    engines = [MagicMock(), MagicMock()]
    for index, engine in enumerate(engines):
        connection = engine.begin.return_value.__enter__.return_value
        connection.scalar.return_value = "pulso" if index == unsafe_connection else "pulso_test"
    with (
        patch.object(conftest, "create_engine", side_effect=engines),
        patch("conftest.command.upgrade") as upgrade,
        pytest.raises(pytest.fail.Exception, match="dedicated pulso_test"),
    ):
        next(unwrap(conftest.db_engine)())
    unsafe = engines[unsafe_connection].begin.return_value.__enter__.return_value
    assert str(unsafe.scalar.call_args.args[0]) == "SELECT current_database()"
    unsafe.execute.assert_not_called()
    upgrade.assert_not_called()
    engines[0].dispose.assert_called_once()
