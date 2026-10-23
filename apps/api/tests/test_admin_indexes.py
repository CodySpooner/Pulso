"""PERF-02: exercise the actual Data Health queries on PostgreSQL fixture history."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.routers.admin import get_host, list_runs
from pulso_core.settings import Settings


def nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from nodes(child)


@contextmanager
def captured(connection: Connection) -> Iterator[list[tuple[str, Any]]]:
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
        yield queries
    finally:
        event.remove(connection, "before_cursor_execute", capture)


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

        with captured(connection) as queries, Session(connection) as session:
            expected = get_host(session, settings)
        assert len(queries) == 3
        assert expected.latest_heartbeat is not None
        assert len(expected.open_gaps) == 50 and expected.next_cursor is not None
        assert len(expected.latest_gap_ends) == 4
        # imp-029 (DEC-133): the per-source summary reads the whole window; the gap page reads
        # limit + 1 rows plus one tie probe and sorts only rows sharing a slot_start (DEC-163).
        for (sql, params), index, direction, rows in zip(
            queries,
            (
                "ix_collection_gaps_open_slot_start",
                "ix_host_heartbeats_at",
                "ix_collection_gaps_open_slot_start",
            ),
            ("Forward", "Backward", "Backward"),
            (2160, 1, 52),
            strict=True,
        ):
            plan = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
            ).scalar_one()[0]["Plan"]
            steps = list(nodes(plan))
            assert not any(step["Node Type"] == "Sort" for step in steps)
            assert all(
                step["Presorted Key"] == ["collection_gaps.slot_start"]
                for step in steps
                if step["Node Type"] == "Incremental Sort"
            )
            scan = next(step for step in steps if step.get("Index Name") == index)
            assert scan["Scan Direction"] == direction
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


@pytest.mark.db
def test_sparse_source_run_pages_scan_only_their_own_runs(db_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        # imp-030 fixture: backup (source 5) owns every 100th run of the older half.
        connection.execute(
            text("""
            INSERT INTO collector_runs (source_id, trigger, queued_at, status)
            SELECT CASE WHEN i <= 100000 AND i % 100 = 0 THEN 5 ELSE 1 + i % 4 END,
                   'manual', now() - (200000 - i) * interval '3 minutes', 'queued'
            FROM generate_series(1, 200000) i
        """)
        )
        for table in ("sources", "collector_runs"):
            connection.execute(text(f"ANALYZE {table}"))
        truth = connection.scalars(
            text("SELECT id FROM collector_runs WHERE source_id = 5 ORDER BY id DESC LIMIT 100")
        ).all()

        with captured(connection) as queries, Session(connection) as session:
            first = list_runs(session, source="backup", cursor=None, limit=50)
            older = list_runs(session, source="backup", cursor=first.next_cursor, limit=50)
        assert [run.id for run in first.items + older.items] == truth
        assert len(queries) == 4  # key lookup, then the page, per call
        for sql, params in queries[1::2]:
            # psycopg prepares repeated statements, so the generic plan must hold too.
            for mode in ("auto", "force_generic_plan"):
                connection.execute(text(f"SET LOCAL plan_cache_mode = {mode}"))
                plan = connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params
                ).scalar_one()[0]["Plan"]
                scan = next(s for s in nodes(plan) if s.get("Relation Name") == "collector_runs")
                assert scan.get("Index Name") == "ix_collector_runs_source_id_id"
                assert scan["Scan Direction"] == "Backward"
                assert scan["Actual Rows"] == 51
                assert scan.get("Rows Removed by Filter", 0) == 0

        command.downgrade(config, "0003")
        indexes = {item["name"] for item in inspect(connection).get_indexes("collector_runs")}
        assert "ix_collector_runs_source_id_id" not in indexes
        with Session(connection) as session:
            assert list_runs(session, source="backup", cursor=None, limit=50) == first
        command.upgrade(config, "head")
