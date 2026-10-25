"""Amazon: source 8 (CSV only, disabled) and its rank observations (DEC-279).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
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
        [{"id": 8, "key": "amazon", "name": "Amazon", "type": "csv", "enabled": False, "phase": 3}],
    )
    op.create_table(
        "amazon_ranks",
        sa.Column("asin", sa.String(length=10), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("rank_kind", sa.String(length=20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("review_count", sa.BigInteger(), nullable=True),
        sa.Column("gtins", sa.Text(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.Column("parser_version", sa.String(length=80), server_default="1", nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_amazon_ranks_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_amazon_ranks_raw_payload_id_raw_payloads"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amazon_ranks")),
        sa.UniqueConstraint(
            "asin",
            "category",
            "rank_kind",
            "observed_for",
            "raw_payload_id",
            "parser_version",
            name=op.f(
                "uq_amazon_ranks_asin_category_rank_kind_observed_for_raw_payload_id_parser_version"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_amazon_ranks_asin_captured_at"),
        "amazon_ranks",
        ["asin", "captured_at"],
        unique=False,
    )
    # History is append-only (AGENTS.md §3); the function comes from 0005.
    op.execute(
        "CREATE TRIGGER amazon_ranks_append_only BEFORE UPDATE OR DELETE ON amazon_ranks "
        "FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()"
    )


def downgrade() -> None:
    op.drop_table("amazon_ranks")
    # Runs, captures and events reference the row, so their foreign keys refuse a lossy downgrade.
    op.execute("DELETE FROM sources WHERE id = 8 AND key = 'amazon'")
