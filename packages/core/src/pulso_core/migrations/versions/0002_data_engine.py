"""Phase 1 collection evidence, replay identity and operational state.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OBSERVATION_KEYS = {
    "listing_snapshots": ("listing_id",),
    "variant_snapshots": ("variant_id",),
    "shipping_options": ("listing_id", "variant_id", "destination_country", "method"),
    "fx_rates": ("date", "base", "quote", "source"),
}
FREIGHT_KEYS = (
    "listing_id",
    "variant_id",
    "origin_country",
    "destination_country",
    "quantity",
    "method",
)


def upgrade() -> None:
    op.add_column("sources", sa.Column("retry_not_before", sa.DateTime(timezone=True)))
    op.add_column("collector_runs", sa.Column("queued_at", sa.DateTime(timezone=True)))
    # Legacy enqueue time is unknown; its start is the earliest recorded run time.
    op.execute("UPDATE collector_runs SET queued_at = started_at")
    op.alter_column("collector_runs", "queued_at", nullable=False, server_default=sa.func.now())
    op.alter_column("collector_runs", "started_at", nullable=True, server_default=None)
    op.alter_column("collector_runs", "status", server_default="queued")
    op.add_column("raw_payloads", sa.Column("template_version", sa.String(80)))
    op.create_index(
        "uq_raw_payloads_import",
        "raw_payloads",
        ["source_id", "sha256", "template_version"],
        unique=True,
        postgresql_where=sa.text("template_version IS NOT NULL"),
    )
    op.add_column(
        "shipping_options", sa.Column("quantity", sa.Integer(), nullable=False, server_default="1")
    )
    for table, keys in OBSERVATION_KEYS.items():
        op.add_column(
            table, sa.Column("parser_version", sa.String(80), nullable=False, server_default="1")
        )
        old_columns = (*keys, "raw_payload_id")
        op.drop_constraint(op.f(f"uq_{table}_{'_'.join(old_columns)}"), table, type_="unique")
        columns = (
            *(FREIGHT_KEYS if table == "shipping_options" else keys),
            "raw_payload_id",
            "parser_version",
        )
        op.create_unique_constraint(
            op.f(f"uq_{table}_{'_'.join(columns)}"),
            table,
            columns,
            postgresql_nulls_not_distinct=True,
        )

    op.create_table(
        "search_trends",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("keyword", sa.Text(), nullable=False),
        sa.Column("geo", sa.CHAR(length=2), nullable=False),
        sa.Column("window", sa.String(length=80), nullable=False),
        sa.Column("granularity", sa.String(length=20), nullable=False),
        sa.Column("metric", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("is_partial", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.String(length=80), server_default="1", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_search_trends_raw_payload_id_raw_payloads"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_search_trends_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_search_trends")),
        sa.UniqueConstraint(
            "source_id",
            "keyword",
            "geo",
            "window",
            "granularity",
            "observed_for",
            "metric",
            "raw_payload_id",
            "parser_version",
            name=op.f(
                "uq_search_trends_source_id_keyword_geo_window_granularity_observed_for_metric_raw_payload_id_parser_version"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_search_trends_keyword_geo_captured_at",
        "search_trends",
        ["keyword", "geo", "captured_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_trends_source_id_captured_at"),
        "search_trends",
        ["source_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "collector_run_targets",
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status <> 'success' OR raw_payload_id IS NOT NULL",
            name=op.f("ck_collector_run_targets_success_evidence"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_collector_run_targets_raw_payload_id_raw_payloads"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["collector_runs.id"],
            name=op.f("fk_collector_run_targets_run_id_collector_runs"),
        ),
        sa.PrimaryKeyConstraint(
            "run_id", "scope", "target_id", name=op.f("pk_collector_run_targets")
        ),
    )
    op.create_index(
        op.f("ix_collector_run_targets_scope_target_id_captured_at"),
        "collector_run_targets",
        ["scope", "target_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "host_heartbeats",
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_host_heartbeats")),
    )
    op.create_index(
        op.f("ix_host_heartbeats_host_at"), "host_heartbeats", ["host", "at"], unique=False
    )
    op.create_table(
        "collection_gaps",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("slot_key", sa.String(length=30), nullable=False),
        sa.Column("slot_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("slot_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=30), nullable=False),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("filled_by_run_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint("slot_end > slot_start", name=op.f("ck_collection_gaps_slot_range")),
        sa.ForeignKeyConstraint(
            ["filled_by_run_id"],
            ["collector_runs.id"],
            name=op.f("fk_collection_gaps_filled_by_run_id_collector_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_collection_gaps_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_gaps")),
        sa.UniqueConstraint(
            "source_id", "slot_key", name=op.f("uq_collection_gaps_source_id_slot_key")
        ),
    )
    op.create_index(
        op.f("ix_collection_gaps_source_id_slot_start"),
        "collection_gaps",
        ["source_id", "slot_start"],
        unique=False,
    )
    op.create_table(
        "source_events",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("actor", sa.String(length=255), server_default="system", nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_source_events_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_events")),
    )
    op.create_index(
        op.f("ix_source_events_source_id_at"), "source_events", ["source_id", "at"], unique=False
    )

    op.execute("""
        CREATE FUNCTION reject_source_event_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'source_events is append-only';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER source_events_append_only BEFORE UPDATE OR DELETE ON source_events
        FOR EACH ROW EXECUTE FUNCTION reject_source_event_mutation()
    """)
    op.execute("""
        CREATE VIEW source_daily_coverage AS
        WITH target_days AS (
            SELECT r.source_id, (t.captured_at AT TIME ZONE 'UTC')::date AS day,
                   t.scope, t.target_id, bool_or(t.status = 'success') AS covered
            FROM collector_run_targets t JOIN collector_runs r ON r.id = t.run_id
            GROUP BY r.source_id, day, t.scope, t.target_id
        ), coverage AS (
            SELECT source_id, day, count(*) AS targets,
                   count(*) FILTER (WHERE covered) AS successful_targets
            FROM target_days GROUP BY source_id, day
        ), runs AS (
            SELECT source_id,
                   (coalesce(started_at, queued_at) AT TIME ZONE 'UTC')::date AS day,
                   count(*) AS runs, sum(rows_inserted) AS rows,
                   bool_or(status = 'running') AS running, bool_or(status = 'queued') AS queued,
                   bool_or(status IN ('failed', 'blocked', 'partial')) AS failed
            FROM collector_runs GROUP BY source_id, day
        ), gaps AS (
            SELECT source_id, d::date AS day,
                   bool_or(filled_by_run_id IS NULL) AS unfilled
            FROM collection_gaps,
                 LATERAL generate_series(
                     date_trunc('day', slot_start AT TIME ZONE 'UTC'),
                     date_trunc('day', (slot_end AT TIME ZONE 'UTC') - interval '1 microsecond'),
                     interval '1 day'
                 ) d
            GROUP BY source_id, day
        ), days AS (
            SELECT source_id, day FROM coverage UNION SELECT source_id, day FROM runs
            UNION SELECT source_id, day FROM gaps
        )
        SELECT d.source_id, d.day,
               CASE
                   WHEN c.successful_targets = c.targets AND c.targets > 0
                        AND NOT coalesce(g.unfilled, false) THEN 'success'
                   WHEN c.successful_targets > 0 THEN 'partial'
                   WHEN g.unfilled THEN 'gap'
                   WHEN r.running THEN 'running'
                   WHEN r.queued THEN 'queued'
                   WHEN r.failed OR c.targets > 0 THEN 'failed'
                   ELSE 'unknown'
               END AS status,
               coalesce(r.runs, 0) AS runs, coalesce(r.rows, 0) AS rows,
               coalesce(c.targets, 0) AS targets,
               coalesce(c.successful_targets, 0) AS successful_targets
        FROM days d LEFT JOIN coverage c USING (source_id, day)
        LEFT JOIN runs r USING (source_id, day) LEFT JOIN gaps g USING (source_id, day)
    """)
    op.bulk_insert(
        sa.table(
            "sources",
            sa.column("id", sa.SmallInteger()),
            sa.column("key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("type", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("phase", sa.SmallInteger()),
        ),
        [
            {
                "id": 5,
                "key": "backup",
                "name": "Backups",
                "type": "internal",
                "enabled": False,
                "phase": 1,
            }
        ],
    )


def downgrade() -> None:
    # Restore restrictive constraints first: incompatible history aborts instead of being deleted.
    op.alter_column("collector_runs", "started_at", nullable=False, server_default=sa.func.now())
    for table, keys in OBSERVATION_KEYS.items():
        columns = (
            *(FREIGHT_KEYS if table == "shipping_options" else keys),
            "raw_payload_id",
            "parser_version",
        )
        op.drop_constraint(op.f(f"uq_{table}_{'_'.join(columns)}"), table, type_="unique")
        old_columns = (*keys, "raw_payload_id")
        op.create_unique_constraint(
            op.f(f"uq_{table}_{'_'.join(old_columns)}"),
            table,
            old_columns,
            postgresql_nulls_not_distinct=True,
        )
        op.drop_column(table, "parser_version")
    op.execute("DROP VIEW source_daily_coverage")
    for table in (
        "source_events",
        "collection_gaps",
        "host_heartbeats",
        "collector_run_targets",
        "search_trends",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_source_event_mutation()")
    op.execute("DELETE FROM sources WHERE id = 5 AND key = 'backup'")
    op.drop_column("shipping_options", "quantity")
    op.drop_index("uq_raw_payloads_import", table_name="raw_payloads")
    op.drop_column("raw_payloads", "template_version")
    op.alter_column("collector_runs", "status", server_default="running")
    op.drop_column("collector_runs", "queued_at")
    op.drop_column("sources", "retry_not_before")
