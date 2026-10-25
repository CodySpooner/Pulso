from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CHAR, BigInteger, DateTime, Table, UniqueConstraint

from pulso_core import models
from pulso_core.db import Base, Observation, WorkspaceOwned


def test_observation_contract() -> None:
    natural_keys = {
        "listing_snapshots": ("listing_id",),
        "variant_snapshots": ("variant_id",),
        "shipping_options": (
            "listing_id",
            "variant_id",
            "origin_country",
            "destination_country",
            "quantity",
            "method",
        ),
        "fx_rates": ("date", "base", "quote", "source"),
        "search_trends": (
            "source_id",
            "keyword",
            "geo",
            "window",
            "granularity",
            "observed_for",
            "metric",
        ),
    }
    observed = []
    for mapper in Base.registry.mappers:
        if issubclass(mapper.class_, Observation):
            table = mapper.local_table
            assert isinstance(table, Table)
            observed.append(table.name)
            assert {"captured_at", "observed_for", "raw_payload_id", "parser_version"} <= set(
                table.c.keys()
            )
            assert all(
                not table.c[name].nullable
                for name in (
                    "captured_at",
                    "observed_for",
                    "raw_payload_id",
                    "parser_version",
                )
            )
            assert table.c.raw_payload_id.foreign_keys
            keys = (*natural_keys[table.name], "raw_payload_id", "parser_version")
            assert any(
                isinstance(c, UniqueConstraint) and tuple(c.columns.keys()) == keys
                for c in table.constraints
            )
            assert any(tuple(i.columns.keys()) == (keys[0], "captured_at") for i in table.indexes)
            if table.name == "shipping_options":
                assert any(
                    isinstance(c, UniqueConstraint)
                    and c.dialect_options["postgresql"]["nulls_not_distinct"]
                    for c in table.constraints
                )
            if table.name == "fx_rates":
                assert tuple(table.primary_key.columns.keys()) == natural_keys[table.name]
    assert set(observed) == {
        "listing_snapshots",
        "variant_snapshots",
        "shipping_options",
        "fx_rates",
        "search_trends",
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


def test_single_migration_head_and_offline_sql(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"), output_buffer=output)
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0007"]
    assert scripts.get_revision("0007").down_revision == "0006"
    assert scripts.get_revision("0006").down_revision == "0005"
    assert scripts.get_revision("0005").down_revision == "0004"
    assert scripts.get_revision("0004").down_revision == "0003"
    assert scripts.get_revision("0003").down_revision == "0002"
    assert scripts.get_revision("0002").down_revision == "0001"
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
    assert "CREATE VIEW source_daily_coverage" in sql
    assert "WHERE template_version IS NOT NULL" in sql
    assert "'backup', 'Backups', 'internal', false" in sql
    assert "CREATE INDEX ix_host_heartbeats_at ON host_heartbeats (at)" in sql
    assert (
        "CREATE INDEX ix_collection_gaps_open_slot_start ON collection_gaps (slot_start) "
        "WHERE filled_by_run_id IS NULL"
    ) in sql
    assert "CREATE INDEX ix_collector_runs_source_id_id ON collector_runs (source_id, id)" in sql
    for table, column in (("images", "embedding"), ("listings", "title_embedding")):
        assert (
            f"CREATE INDEX ix_{table}_{column} ON {table} USING hnsw ({column} vector_cosine_ops)"
        ) in sql
        assert f"ALTER TABLE {table} ADD COLUMN {column} VECTOR(512)" in sql
    assert "BEFORE UPDATE OR DELETE ON match_decisions" in sql


def test_queue_and_import_identity_contract() -> None:
    runs = models.CollectorRun.__table__
    assert runs.c.started_at.nullable and runs.c.started_at.server_default is None
    assert not runs.c.queued_at.nullable
    assert str(runs.c.status.server_default.arg) == "queued"
    payloads = models.RawPayload.__table__
    assert isinstance(payloads, Table)
    assert payloads.c.template_version.nullable
    identity = next(i for i in payloads.indexes if i.unique)
    assert tuple(identity.columns.keys()) == ("source_id", "sha256", "template_version")
    assert str(identity.dialect_options["postgresql"]["where"]) == "template_version IS NOT NULL"
    targets = models.CollectorRunTarget.__table__
    assert isinstance(targets, Table)
    assert any(
        tuple(i.columns.keys()) == ("scope", "target_id", "captured_at") for i in targets.indexes
    )
