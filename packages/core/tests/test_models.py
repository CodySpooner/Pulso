from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CHAR, BigInteger, DateTime, Table, UniqueConstraint

from pulso_core import models
from pulso_core.db import Base, Observation, WorkspaceOwned


def test_observation_contract() -> None:
    observed = []
    for mapper in Base.registry.mappers:
        if issubclass(mapper.class_, Observation):
            table = mapper.local_table
            assert isinstance(table, Table)
            observed.append(table.name)
            assert {"captured_at", "observed_for", "raw_payload_id"} <= set(table.c.keys())
            assert all(
                not table.c[name].nullable
                for name in (
                    "captured_at",
                    "observed_for",
                    "raw_payload_id",
                )
            )
            assert table.c.raw_payload_id.foreign_keys
            keys = (*mapper.class_.observation_keys, "raw_payload_id")
            assert any(
                isinstance(c, UniqueConstraint) and tuple(c.columns.keys()) == keys
                for c in table.constraints
            )
            assert any(tuple(i.columns.keys()) == (keys[0], "captured_at") for i in table.indexes)
    assert set(observed) == {
        "listing_snapshots",
        "variant_snapshots",
        "shipping_options",
        "fx_rates",
    }


def test_workspace_money_and_utc_contract() -> None:
    for mapper in Base.registry.mappers:
        table = mapper.local_table
        assert isinstance(table, Table)
        if issubclass(mapper.class_, WorkspaceOwned):
            assert not table.c.workspace_id.nullable
            assert any("workspace_id" in i.columns.keys() for i in table.indexes)
        for column in table.columns:
            if column.name.endswith("_minor"):
                assert isinstance(column.type, BigInteger)
                assert isinstance(table.c.currency.type, CHAR)
                assert table.c.currency.type.length == 3
            if isinstance(column.type, DateTime):
                assert column.type.timezone
            if any(word in column.name for word in ("price", "cost", "fee", "cpa")):
                assert not column.type.__class__.__name__ == "Numeric"
    assert models.Listing.__table__.c.get("price") is None


def test_single_frozen_migration_and_offline_sql() -> None:
    output = StringIO()
    config = Config("alembic.ini", output_buffer=output)
    assert ScriptDirectory.from_config(config).get_heads() == ["0001"]
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm" in sql
    assert sql.count("CREATE TABLE ") == len(Base.metadata.tables) + 1
    assert "UNIQUE NULLS NOT DISTINCT" in sql
    assert "num_nonnulls(store_id, supplier_id) <= 1" in sql
    assert "WHERE status = 'success' AND trigger IN ('schedule', 'catchup')" in sql
    assert "'Shopify stores', 'public_endpoint', false" in sql
    assert sql.count("ADD CONSTRAINT fk_products_main_image_id_images") == 1
