"""Watchlists (WF-2): the workspace's named product lists and their items (DEC-314).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_watchlists_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_watchlists")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_watchlists_workspace_id_id")),
        sa.UniqueConstraint("workspace_id", "name", name=op.f("uq_watchlists_workspace_id_name")),
    )
    op.create_index(op.f("ix_watchlists_workspace_id"), "watchlists", ["workspace_id"])
    op.create_table(
        "watchlist_items",
        sa.Column("watchlist_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_watchlist_items_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "watchlist_id"],
            ["watchlists.workspace_id", "watchlists.id"],
            name=op.f("fk_watchlist_items_workspace_id_watchlist_id_watchlists"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_watchlist_items_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("watchlist_id", "product_id", name=op.f("pk_watchlist_items")),
    )
    op.create_index(op.f("ix_watchlist_items_workspace_id"), "watchlist_items", ["workspace_id"])


def downgrade() -> None:
    # The lists are the owner's own picks: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM watchlists) THEN
                RAISE EXCEPTION 'watchlists holds the owner''s lists; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")
