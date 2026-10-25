"""Boards (WF-3): the workspace's boards of product ideas and their ordered, noted items
(DEC-319).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "boards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_boards_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_boards")),
        sa.UniqueConstraint("workspace_id", "id", name=op.f("uq_boards_workspace_id_id")),
        sa.UniqueConstraint("workspace_id", "name", name=op.f("uq_boards_workspace_id_name")),
    )
    op.create_index(op.f("ix_boards_workspace_id"), "boards", ["workspace_id"])
    op.create_table(
        "board_items",
        sa.Column("board_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_board_items_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "board_id"],
            ["boards.workspace_id", "boards.id"],
            name=op.f("fk_board_items_workspace_id_board_id_boards"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_board_items_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("board_id", "product_id", name=op.f("pk_board_items")),
    )
    op.create_index(op.f("ix_board_items_workspace_id"), "board_items", ["workspace_id"])


def downgrade() -> None:
    # The boards are the owner's own picks and notes: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM boards) THEN
                RAISE EXCEPTION 'boards holds the owner''s boards; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("board_items")
    op.drop_table("boards")
