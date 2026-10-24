"""Phase 2: embeddings, matching, category mappings, notes/tags, daily features (DEC-237).

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 512  # OpenCLIP ViT-B-32 laion2b_s34b_b79k (DEC-237)


def upgrade() -> None:
    for table, column in (("images", "embedding"), ("listings", "title_embedding")):
        op.add_column(table, sa.Column(column, Vector(EMBEDDING_DIM), nullable=True))
        op.create_index(
            op.f(f"ix_{table}_{column}"),
            table,
            [column],
            postgresql_using="hnsw",
            postgresql_ops={column: "vector_cosine_ops"},
        )
    op.create_table(
        "match_candidates",
        sa.Column("listing_a_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_b_id", sa.BigInteger(), nullable=False),
        sa.Column("image_cos", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("title_cos", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("phash_sim", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("price_sane", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("scorer_version", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'merged', 'split')",
            name=op.f("ck_match_candidates_status_values"),
        ),
        sa.CheckConstraint(
            "listing_a_id < listing_b_id", name=op.f("ck_match_candidates_ordered_pair")
        ),
        sa.ForeignKeyConstraint(
            ["listing_a_id"],
            ["listings.id"],
            name=op.f("fk_match_candidates_listing_a_id_listings"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_b_id"],
            ["listings.id"],
            name=op.f("fk_match_candidates_listing_b_id_listings"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_candidates")),
        sa.UniqueConstraint(
            "listing_a_id",
            "listing_b_id",
            name=op.f("uq_match_candidates_listing_a_id_listing_b_id"),
        ),
    )
    op.create_index(
        op.f("ix_match_candidates_status_score"), "match_candidates", ["status", "score"]
    )
    op.create_table(
        "match_decisions",
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("from_product_id", sa.Uuid(), nullable=True),
        sa.Column("to_product_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_id", sa.BigInteger(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "action IN ('link', 'unlink', 'merge', 'split', 'accept', 'reject')",
            name=op.f("ck_match_decisions_action_values"),
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["match_candidates.id"],
            name=op.f("fk_match_decisions_candidate_id_match_candidates"),
        ),
        sa.ForeignKeyConstraint(
            ["from_product_id"],
            ["products.id"],
            name=op.f("fk_match_decisions_from_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_match_decisions_listing_id_listings")
        ),
        sa.ForeignKeyConstraint(
            ["to_product_id"],
            ["products.id"],
            name=op.f("fk_match_decisions_to_product_id_products"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_match_decisions")),
    )
    op.create_index(
        op.f("ix_match_decisions_listing_id_decided_at"),
        "match_decisions",
        ["listing_id", "decided_at"],
    )
    # Generic, so later append-only tables (scores, forecasts) can reuse it.
    op.execute("""
        CREATE FUNCTION reject_append_only_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER match_decisions_append_only BEFORE UPDATE OR DELETE ON match_decisions
        FOR EACH ROW EXECUTE FUNCTION reject_append_only_mutation()
    """)
    op.execute("""
        CREATE TRIGGER match_decisions_no_truncate BEFORE TRUNCATE ON match_decisions
        FOR EACH STATEMENT EXECUTE FUNCTION reject_append_only_mutation()
    """)
    op.create_table(
        "category_mappings",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("source_category", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("mapping_source", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "mapping_source IN ('rule', 'ai', 'manual')",
            name=op.f("ck_category_mappings_mapping_source_values"),
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["categories.id"],
            name=op.f("fk_category_mappings_category_id_categories"),
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_category_mappings_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("source_id", "source_category", name=op.f("pk_category_mappings")),
    )
    op.create_table(
        "product_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_product_notes_author_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_product_notes_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_product_notes_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_notes")),
    )
    op.create_index(op.f("ix_product_notes_workspace_id"), "product_notes", ["workspace_id"])
    op.create_index(
        op.f("ix_product_notes_workspace_id_product_id"),
        "product_notes",
        ["workspace_id", "product_id"],
    )
    op.create_table(
        "product_tags",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("tag", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_product_tags_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_product_tags_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("workspace_id", "product_id", "tag", name=op.f("pk_product_tags")),
    )
    op.create_index(op.f("ix_product_tags_workspace_id"), "product_tags", ["workspace_id"])
    op.create_table(
        "product_daily_features",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("feature_date", sa.Date(), nullable=False),
        sa.Column("family", sa.String(length=20), nullable=False),
        sa.Column("feature_version", sa.String(length=80), nullable=False),
        sa.Column("velocity_7d", sa.Double(), nullable=True),
        sa.Column("growth_7d", sa.Double(), nullable=True),
        sa.Column("coverage", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("has_gap", sa.Boolean(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "coverage BETWEEN 0 AND 1", name=op.f("ck_product_daily_features_coverage_range")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_daily_features_product_id_products"),
        ),
        sa.PrimaryKeyConstraint(
            "product_id",
            "feature_date",
            "family",
            "feature_version",
            name=op.f("pk_product_daily_features"),
        ),
    )
    op.add_column("settings", sa.Column("duty_default_bps", sa.Integer(), nullable=True))
    op.add_column(
        "settings", sa.Column("returns_bps", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "settings",
        sa.Column("customs_fee_minor", sa.BigInteger(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        op.f("ck_settings_duty_default_range"), "settings", "duty_default_bps >= 0"
    )
    op.create_check_constraint(
        op.f("ck_settings_returns_range"), "settings", "returns_bps BETWEEN 0 AND 10000"
    )
    op.create_check_constraint(
        op.f("ck_settings_customs_fee_range"), "settings", "customs_fee_minor >= 0"
    )


def downgrade() -> None:
    # Embeddings, candidates, rule/AI mappings and features are recomputable; these are not.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM match_decisions)
               OR EXISTS (SELECT 1 FROM product_notes)
               OR EXISTS (SELECT 1 FROM product_tags)
               OR EXISTS (SELECT 1 FROM category_mappings WHERE mapping_source = 'manual')
               OR EXISTS (
                   SELECT 1 FROM settings
                   WHERE duty_default_bps IS NOT NULL OR returns_bps <> 0
                         OR customs_fee_minor <> 0
               )
            THEN
                RAISE EXCEPTION
                    '0005 downgrade would discard Phase 2 owner input; restore a backup instead';
            END IF;
        END $$
    """)
    for column in ("customs_fee_minor", "returns_bps", "duty_default_bps"):
        op.drop_column("settings", column)  # drops its CHECK too
    for table in (
        "product_daily_features",
        "product_tags",
        "product_notes",
        "category_mappings",
        "match_decisions",
        "match_candidates",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION reject_append_only_mutation()")
    op.drop_column("listings", "title_embedding")  # drops its HNSW index too
    op.drop_column("images", "embedding")
