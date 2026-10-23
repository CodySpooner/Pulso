"""Index source-filtered Data Health run pages by (source_id, id) (DEC-158)."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_collector_runs_source_id_id", "collector_runs", ["source_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_collector_runs_source_id_id", table_name="collector_runs")
