"""Workspace brand rules for Google popular: hide a brand, or show one the major-brand rule hides
(DEC-277). Current preference state, replaced and deleted in place: not history.

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "popular_brand_rules",
        sa.Column("brand_norm", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=4), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('hide', 'show')", name=op.f("ck_popular_brand_rules_action")
        ),
        sa.CheckConstraint(
            "brand_norm = lower(brand)", name=op.f("ck_popular_brand_rules_brand_norm")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_popular_brand_rules_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_popular_brand_rules_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("workspace_id", "brand_norm", name=op.f("pk_popular_brand_rules")),
    )
    op.create_index(
        op.f("ix_popular_brand_rules_workspace_id"), "popular_brand_rules", ["workspace_id"]
    )


def downgrade() -> None:
    # The owner's brand list isn't recomputable.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM popular_brand_rules) THEN
                RAISE EXCEPTION
                    '0011 downgrade would discard the owner''s brand rules; restore a backup';
            END IF;
        END $$
    """)
    op.drop_table("popular_brand_rules")
