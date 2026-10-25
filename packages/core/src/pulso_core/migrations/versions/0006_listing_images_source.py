"""Register the listing image fetcher as source 6, disabled (DEC-240).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.bulk_insert(
        sa.table(
            "sources",
            sa.column("id", sa.SmallInteger()),
            sa.column("key", sa.String()),
            sa.column("name", sa.String()),
            sa.column("type", sa.String()),
            sa.column("enabled", sa.Boolean()),
            sa.column("phase", sa.SmallInteger()),
        ),
        [
            {
                "id": 6,
                "key": "listing_images",
                "name": "Listing images",
                "type": "public_endpoint",
                "enabled": False,
                "phase": 2,
            }
        ],
    )


def downgrade() -> None:
    # Runs, captures and events reference the row, so their foreign keys refuse a lossy downgrade.
    op.execute("DELETE FROM sources WHERE id = 6 AND key = 'listing_images'")
