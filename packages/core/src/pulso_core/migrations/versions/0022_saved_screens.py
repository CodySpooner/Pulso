"""Saved screens (WF-1 part a): the workspace's saved Screener definitions (DEC-336).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_screens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_saved_screens_version_range")),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_saved_screens_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_saved_screens")),
        sa.UniqueConstraint(
            "workspace_id", "name", name=op.f("uq_saved_screens_workspace_id_name")
        ),
    )
    op.create_index(op.f("ix_saved_screens_workspace_id"), "saved_screens", ["workspace_id"])


def downgrade() -> None:
    # The screens are the owner's own definitions: refuse a lossy downgrade.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM saved_screens) THEN
                RAISE EXCEPTION 'saved_screens holds rows; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("saved_screens")
