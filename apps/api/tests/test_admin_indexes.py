"""PERF-02: exercise the actual host queries on PostgreSQL fixture history."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.routers.admin import get_host
from pulso_core.settings import Settings


def nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


@pytest.mark.db
def test_host_indexes_bound_reads_and_preserve_rows_on_downgrade(
    db_engine: Engine, settings: Settings
) -> None:
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        connection.execute(
            text("INSERT INTO collector_runs (source_id, trigger) VALUES (1, 'csv')")
        )
        connection.execute(
            text("""
            INSERT INTO host_heartbeats (host, at)
            SELECT 'fixture-' || i % 3, now() - (200000 - i) * interval '5 minutes'
            FROM generate_series(1, 200000) i
        """)
        )
        connection.execute(
            text("""
            INSERT INTO collection_gaps
                (source_id, slot_key, slot_start, slot_end, reason, filled_by_run_id)
            SELECT 1 + (i / 20) % 4, 'fixture-' || i,
                   now() - (200001 - i) * interval '3 minutes',
                   now() - (200000 - i) * interval '3 minutes', 'host_offline',
                   CASE WHEN i % 20 = 0 THEN NULL ELSE 1 END
            FROM generate_series(1, 200000) i
        """)
        )
        for table in ("sources", "host_heartbeats", "collection_gaps"):
            connection.execute(text(f"ANALYZE {table}"))

        queries: list[tuple[str, Any]] = []

        def capture(
            conn: Connection,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            queries.append((statement, parameters))

        event.listen(connection, "before_cursor_execute", capture)
        try:
            with Session(connection) as session:
                expected = get_host(session, settings)
        finally:
            event.remove(connection, "before_cursor_execute", capture)
        assert len(queries) == 2
        assert expected.latest_heartbeat is not None
        assert len(expected.open_gaps) == 2160
        for (sql, params), index, rows in zip(
            queries,
            ("ix_host_heartbeats_at", "ix_collection_gaps_open_slot_start"),
            (1, 2160),
            strict=True,
        ):
            plan = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
            ).scalar_one()[0]["Plan"]
            steps = list(nodes(plan))
            assert not any(step["Node Type"] in ("Sort", "Incremental Sort") for step in steps)
            scan = next(step for step in steps if step.get("Index Name") == index)
            assert scan["Scan Direction"] == "Backward"
            assert scan["Actual Rows"] == rows
            assert scan.get("Rows Removed by Filter", 0) == 0

        command.downgrade(config, "0002")
        for table, index in (
            ("host_heartbeats", "ix_host_heartbeats_at"),
            ("collection_gaps", "ix_collection_gaps_open_slot_start"),
        ):
            assert index not in {item["name"] for item in inspect(connection).get_indexes(table)}
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 200000
        with Session(connection) as session:
            assert get_host(session, settings) == expected
        command.upgrade(config, "head")
        with Session(connection) as session:
            assert get_host(session, settings) == expected
