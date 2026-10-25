from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, delete, insert, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pulso_core.models import Product, ProductKeyword, User, Workspace

pytestmark = pytest.mark.db

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")


def keyword_row(connection: Connection, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "workspace_id": connection.execute(
            insert(Workspace).values(name="A").returning(Workspace.id)
        ).scalar_one(),
        "product_id": connection.execute(
            insert(Product).values(name="Sunset lamp").returning(Product.id)
        ).scalar_one(),
        "decided_by": connection.execute(
            insert(User).values(clerk_user_id="user_a").returning(User.id)
        ).scalar_one(),
        "keyword": "sunset lamp",
        "relevance": 0.833,
        "source": "title",
        "status": "confirmed",
    }
    return row | overrides


def test_a_keyword_decision_changes_but_its_row_is_never_deleted(db_engine: Engine) -> None:
    """DEC-281: a new decision updates the row; DELETE and TRUNCATE are refused, and a downgrade
    that would drop decisions refuses too."""
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        connection.execute(insert(ProductKeyword).values(keyword_row(connection)))
        connection.execute(update(ProductKeyword).values(status="rejected"))
        for statement, match in (
            (delete(ProductKeyword), "never deleted"),
            (text("TRUNCATE product_keywords"), "never deleted"),
        ):
            with pytest.raises(DBAPIError, match=match), connection.begin_nested():
                connection.execute(statement)
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0012")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0019"
        assert connection.scalar(text("SELECT status FROM product_keywords")) == "rejected"


@pytest.mark.parametrize(
    "overrides",
    [{"status": "pending"}, {"source": "ai"}, {"relevance": 1.5}, {"workspace_id": None}],
    ids=["status", "source", "relevance", "workspace"],
)
def test_keyword_rows_hold_only_known_values(
    db_engine: Engine, overrides: dict[str, object]
) -> None:
    with db_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(insert(ProductKeyword).values(keyword_row(connection, **overrides)))
