"""AliExpress: source 9, disabled, for the live lookup's shared block state (DEC-283, DEC-289).

DEC-037: the row is the only thing stored; lookups live in Redis for 24 h.
Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
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
                "id": 9,
                "key": "aliexpress",
                "name": "AliExpress",
                "type": "official_api",
                "enabled": False,
                "phase": 3,
            }
        ],
    )


def downgrade() -> None:
    # A disable event references the row, so its foreign key refuses a lossy downgrade.
    op.execute("DELETE FROM sources WHERE id = 9 AND key = 'aliexpress'")
