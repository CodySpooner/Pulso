"""saved_screens (migration 0022, DEC-336): a name per workspace, and a guarded downgrade."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pulso_core.models import SavedScreen, Workspace

pytestmark = pytest.mark.db

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")


def test_names_versions_and_the_lossy_downgrade_guard(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        a, b = (
            connection.scalar(insert(Workspace).values(name=name).returning(Workspace.id))
            for name in "AB"
        )
        screen = {"name": "Early", "version": 1, "definition": {}}
        connection.execute(insert(SavedScreen).values(workspace_id=a, **screen))
        connection.execute(insert(SavedScreen).values(workspace_id=b, **screen))  # B's own
        for values in ({"workspace_id": a}, {"workspace_id": a, "name": "V0", "version": 0}):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(SavedScreen).values({**screen, **values}))
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0021")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0022"
        connection.execute(text("DELETE FROM saved_screens"))
        command.downgrade(config, "0021")
        assert connection.scalar(text("SELECT to_regclass('saved_screens')")) is None
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT to_regclass('saved_screens')")) is not None
