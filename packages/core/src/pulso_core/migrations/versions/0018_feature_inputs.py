"""Phase 4 FS-1: non-demand inputs and per-family gap flags on product_daily_features (DEC-311).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("features", "gap_flags"):
        op.add_column(
            "product_daily_features",
            sa.Column(column, postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )


def downgrade() -> None:
    # Rows from feature version 002 hold their inputs only in these columns.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM product_daily_features WHERE gap_flags IS NOT NULL) THEN
                RAISE EXCEPTION 'feature rows hold gap flags; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_column("product_daily_features", "gap_flags")
    op.drop_column("product_daily_features", "features")
