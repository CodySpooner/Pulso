"""Global search: pg_trgm GIN indexes on the searched names and titles (DEC-252).

Frozen schema: do not import live application models into a revision.
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

COLUMNS = (
    ("products", "name"),
    ("listings", "title"),
    ("stores", "domain"),
    ("stores", "myshopify_domain"),
    ("suppliers", "name"),
)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")  # 0001 installs it already
    for table, column in COLUMNS:
        op.create_index(
            op.f(f"ix_{table}_{column}"),
            table,
            [column],
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    for table, column in COLUMNS:
        op.drop_index(op.f(f"ix_{table}_{column}"), table_name=table)
