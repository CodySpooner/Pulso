"""Index measured Data Health host queries (DEC-125)."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_host_heartbeats_at", "host_heartbeats", ["at"])
    op.create_index(
        "ix_collection_gaps_open_slot_start",
        "collection_gaps",
        ["slot_start"],
        postgresql_where=sa.text("filled_by_run_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_collection_gaps_open_slot_start", table_name="collection_gaps")
    op.drop_index("ix_host_heartbeats_at", table_name="host_heartbeats")
