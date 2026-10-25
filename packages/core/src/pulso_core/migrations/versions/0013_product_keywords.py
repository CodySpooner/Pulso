"""Product keywords (KW-1): the workspace's confirmed and rejected search keywords (DEC-281).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_keywords",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("keyword", sa.String(length=100), nullable=False),
        sa.Column("relevance", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column(
            "decided_at",
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
        sa.CheckConstraint(
            "relevance BETWEEN 0 AND 1", name=op.f("ck_product_keywords_relevance_range")
        ),
        sa.CheckConstraint(
            "source IN ('title', 'manual')", name=op.f("ck_product_keywords_source_values")
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'rejected')", name=op.f("ck_product_keywords_status_values")
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["users.id"], name=op.f("fk_product_keywords_decided_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_product_keywords_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_product_keywords_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id", "product_id", "keyword", name=op.f("pk_product_keywords")
        ),
    )
    op.create_index(op.f("ix_product_keywords_workspace_id"), "product_keywords", ["workspace_id"])
    # A decision is changed by deciding again, never by deleting the row (DEC-281).
    op.execute("""
        CREATE FUNCTION reject_product_keyword_delete() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'product_keywords rows are never deleted: reject the keyword instead';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER product_keywords_no_delete BEFORE DELETE ON product_keywords
        FOR EACH ROW EXECUTE FUNCTION reject_product_keyword_delete()
    """)
    op.execute("""
        CREATE TRIGGER product_keywords_no_truncate BEFORE TRUNCATE ON product_keywords
        FOR EACH STATEMENT EXECUTE FUNCTION reject_product_keyword_delete()
    """)


def downgrade() -> None:
    # The rows are the owner's decisions: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM product_keywords) THEN
                RAISE EXCEPTION 'product_keywords holds decisions; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("product_keywords")
    op.execute("DROP FUNCTION reject_product_keyword_delete()")
