"""Phase 4: the append-only market `scores` table (SPEC §7, DEC-040, DEC-306).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scores",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Numeric(precision=5, scale=1), nullable=True),
        sa.Column("stage", sa.String(length=20), nullable=True),
        sa.Column("explanation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "kind IN ('trend', 'saturation', 'lifecycle', 'risk', 'refund_risk')",
            name=op.f("ck_scores_kind_values"),
        ),
        sa.CheckConstraint("value BETWEEN 0 AND 100", name=op.f("ck_scores_value_range")),
        sa.CheckConstraint(
            "stage IN ('emerging', 'rising', 'peaking', 'declining', 'dead')",
            name=op.f("ck_scores_stage_values"),
        ),
        sa.CheckConstraint(
            "CASE WHEN kind = 'lifecycle' THEN value IS NULL ELSE stage IS NULL END",
            name=op.f("ck_scores_value_or_stage"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_scores_product_id_products")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scores")),
        sa.UniqueConstraint(
            "kind",
            "product_id",
            "date",
            "model_version",
            name=op.f("uq_scores_kind_product_id_date_model_version"),
        ),
    )
    # History is append-only (AGENTS.md §3); the function comes from 0005.
    op.execute(
        "CREATE TRIGGER scores_append_only BEFORE UPDATE OR DELETE ON scores "
        "FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()"
    )
    op.execute(
        "CREATE TRIGGER scores_no_truncate BEFORE TRUNCATE ON scores "
        "FOR EACH STATEMENT EXECUTE FUNCTION reject_append_only_mutation()"
    )


def downgrade() -> None:
    # Scores are never backfilled (vault Score Definitions §8): dropped rows can't come back.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM scores) THEN
                RAISE EXCEPTION 'scores holds live history; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.drop_table("scores")
