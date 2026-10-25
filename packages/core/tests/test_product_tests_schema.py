"""product_tests (migration 0017, DEC-312): the Testing Board's rows, guarded in the database."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import insert, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pulso_core.models import Product, ProductTest, Workspace

pytestmark = pytest.mark.db

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")


def test_checks_and_the_lossy_downgrade_guard(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        ids = {
            "workspace_id": connection.scalar(
                insert(Workspace).values(name="A").returning(Workspace.id)
            ),
            "product_id": connection.scalar(insert(Product).values(name="P").returning(Product.id)),
        }
        for values in (
            {"stage": "paused"},
            {"stage": "killed"},  # no kill reason
            {"stage": "idea", "kill_reason": "other"},
            {"kill_reason": "bored", "stage": "killed"},
            {"ad_spend_minor": -1},
            {"started_on": "2026-10-20", "ended_on": "2026-10-19"},
            {"currency": "XXX"},
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(insert(ProductTest).values(**ids, **values))
        connection.execute(insert(ProductTest).values(**ids))
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0016")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0019"
        connection.execute(text("DELETE FROM product_tests"))
        command.downgrade(config, "0016")
        assert connection.scalar(text("SELECT to_regclass('product_tests')")) is None
        command.upgrade(config, "head")
