from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, delete, func, insert, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    ProductKeyword,
    RawPayload,
    Supplier,
    User,
    Workspace,
)

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
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024"
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


def test_0024_refuses_a_downgrade_over_cj_stock_rows(db_engine: Engine) -> None:
    """DEC-348: 0023's view would read a CJ stock row as a listing's latest price, and none."""
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection

        def new(table: Any, **values: object) -> Any:
            return connection.execute(insert(table).values(values).returning(table.id)).scalar()

        run = new(CollectorRun, source_id=2, trigger="fixture", status="success")
        payload = new(
            RawPayload, source_id=2, run_id=run, captured_at=func.now(), bytes=1, sha256="0" * 64,
            request={"endpoint": "/product/stock/getInventoryByPid"},
        )  # fmt: skip
        supplier = new(Supplier, platform="cj", external_id="cj", name="CJ Dropshipping")
        listing = new(
            Listing, source_id=2, external_id="p", url="https://cj.example.test/p",
            title="Sunset lamp", supplier_id=supplier,
        )  # fmt: skip
        new(
            ListingSnapshot, listing_id=listing, raw_payload_id=payload, captured_at=func.now(),
            observed_for=func.current_date(), parser_version="cj-tracked-v1", values_hash="s",
            currency="USD", stock=0,
        )  # fmt: skip
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0023")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024"
