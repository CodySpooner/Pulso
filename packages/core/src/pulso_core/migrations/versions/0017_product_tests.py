"""Product tests (WF-5 part a): the Testing Board's workspace tests, with an immutable start
snapshot (R-21, DEC-312). CPA and ROAS are computed on read, never stored.

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_tests",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("stage", sa.String(length=20), server_default="idea", nullable=False),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("ended_on", sa.Date(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), server_default="USD", nullable=False),
        sa.Column("ad_spend_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("revenue_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("orders", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("kill_reason", sa.String(length=40), nullable=True),
        sa.Column("start_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "(stage = 'killed') = (kill_reason IS NOT NULL)",
            name=op.f("ck_product_tests_kill_reason_killed"),
        ),
        sa.CheckConstraint(
            "kill_reason IN ('no_sales_over_stop_loss', 'cpa_above_break_even', "
            "'low_ctr_creatives', 'supplier_issue', 'sample_quality', 'margin_too_thin', "
            "'saturated', 'ad_account_rejection', 'other')",
            name=op.f("ck_product_tests_kill_reason_values"),
        ),
        sa.CheckConstraint(
            "stage IN ('idea', 'researching', 'testing', 'winner', 'killed')",
            name=op.f("ck_product_tests_stage_values"),
        ),
        sa.CheckConstraint(
            "ad_spend_minor >= 0 AND revenue_minor >= 0 AND orders >= 0",
            name=op.f("ck_product_tests_metrics_range"),
        ),
        sa.CheckConstraint("ended_on >= started_on", name=op.f("ck_product_tests_date_order")),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_product_tests_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_product_tests_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_product_tests_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_tests")),
    )
    op.create_index(op.f("ix_product_tests_workspace_id"), "product_tests", ["workspace_id"])
    # One open test per product (Idea, Researching or Testing) in a workspace.
    op.create_index(
        "uq_product_tests_open",
        "product_tests",
        ["workspace_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("stage IN ('idea', 'researching', 'testing')"),
    )
    # R-21: the economics a test started with are never rewritten.
    op.execute("""
        CREATE FUNCTION keep_product_test_start_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.start_snapshot IS NOT NULL
                AND NEW.start_snapshot IS DISTINCT FROM OLD.start_snapshot THEN
                RAISE EXCEPTION 'product_tests.start_snapshot is immutable once taken';
            END IF;
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER product_tests_keep_start_snapshot BEFORE UPDATE ON product_tests
        FOR EACH ROW EXECUTE FUNCTION keep_product_test_start_snapshot()
    """)


def downgrade() -> None:
    # The rows are the owner's test records: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM product_tests) THEN
                RAISE EXCEPTION 'product_tests holds test records; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("product_tests")
    op.execute("DROP FUNCTION keep_product_test_start_snapshot()")
