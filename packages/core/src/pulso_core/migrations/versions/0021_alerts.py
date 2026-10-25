"""Alerts (WF-4 part a): the workspace's alert rules and the alerts they fire (DEC-324).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("muted_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("armed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target_type IN ('product', 'watchlist', 'store', 'saved_screen', 'supplier_offer', "
            "'test', 'all')",
            name=op.f("ck_alert_rules_target_type_values"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_alert_rules_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alert_rules")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_alert_rules_workspace_id_id")),
    )
    op.create_index(op.f("ix_alert_rules_workspace_id"), "alert_rules", ["workspace_id"])
    op.create_table(
        "alerts",
        sa.Column("rule_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=30), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "rule_id"],
            ["alert_rules.workspace_id", "alert_rules.id"],
            name=op.f("fk_alerts_workspace_id_rule_id_alert_rules"),
            ondelete="SET NULL (rule_id)",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_alerts_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_alerts")),
        sa.UniqueConstraint("dedupe_key", name=op.f("uq_alerts_dedupe_key")),
    )
    op.create_index(op.f("ix_alerts_workspace_id"), "alerts", ["workspace_id"])
    op.create_index(
        op.f("ix_alerts_workspace_id_fired_at_id"), "alerts", ["workspace_id", "fired_at", "id"]
    )


def downgrade() -> None:
    # The rules are the owner's and the alerts their history: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM alert_rules) OR EXISTS (SELECT 1 FROM alerts) THEN
                RAISE EXCEPTION 'alert_rules or alerts holds rows; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("alerts")
    op.drop_table("alert_rules")
