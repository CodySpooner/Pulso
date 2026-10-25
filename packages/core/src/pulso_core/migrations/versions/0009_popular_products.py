"""Merchant Center Popular products: source 7 (CSV only, disabled) and its observations (DEC-267).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
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
                "id": 7,
                "key": "merchant_bestsellers",
                "name": "Google Merchant Center Popular products",
                "type": "csv",
                "enabled": False,
                "phase": 2,
            }
        ],
    )
    op.create_table(
        "popular_products",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("country", sa.CHAR(length=2), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("previous_rank", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("brand", sa.Text(), nullable=True),
        sa.Column("availability", sa.Text(), nullable=True),
        sa.Column("relative_demand", sa.Text(), nullable=True),
        sa.Column("relative_demand_change", sa.Text(), nullable=True),
        sa.Column("gtins", sa.Text(), nullable=True),
        sa.Column("price_min_minor", sa.BigInteger(), nullable=True),
        sa.Column("price_max_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=True),
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
            ["currency"],
            ["currencies.code"],
            name=op.f("fk_popular_products_currency_currencies"),
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_popular_products_raw_payload_id_raw_payloads"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_popular_products_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_popular_products")),
        sa.UniqueConstraint(
            "source_id",
            "country",
            "category",
            "observed_for",
            "rank",
            "raw_payload_id",
            "parser_version",
            name=op.f(
                "uq_popular_products_source_id_country_category_observed_for_rank_raw_payload_id_parser_version"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_popular_products_source_id_captured_at"),
        "popular_products",
        ["source_id", "captured_at"],
        unique=False,
    )
    # History is append-only (AGENTS.md §3); the function comes from 0005.
    op.execute(
        "CREATE TRIGGER popular_products_append_only BEFORE UPDATE OR DELETE ON popular_products "
        "FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()"
    )


def downgrade() -> None:
    op.drop_table("popular_products")
    # Runs, captures and events reference the row, so their foreign keys refuse a lossy downgrade.
    op.execute("DELETE FROM sources WHERE id = 7 AND key = 'merchant_bestsellers'")
