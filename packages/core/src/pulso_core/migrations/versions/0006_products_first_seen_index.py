"""Discover's newest sort: a partial (first_seen_at, id) index on unmerged products (DEC-239).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ascending: Postgres scans it backward for ORDER BY first_seen_at DESC, id DESC (DEC-158).
    op.create_index(
        "ix_products_first_seen_at_id",
        "products",
        ["first_seen_at", "id"],
        postgresql_where=sa.text("merged_into_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_first_seen_at_id", table_name="products")
