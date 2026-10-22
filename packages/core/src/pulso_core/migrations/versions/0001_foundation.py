"""Phase 0 Core, Catalog, Vendors and workspace foundation.

Frozen schema: do not import live application models into a revision.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["categories.id"], name=op.f("fk_categories_parent_id_categories")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_categories")),
    )
    op.create_table(
        "currencies",
        sa.Column("code", sa.CHAR(length=3), nullable=False),
        sa.Column("exponent", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("exponent BETWEEN 0 AND 3", name=op.f("ck_currencies_exponent_range")),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_currencies")),
    )
    op.create_table(
        "sources",
        sa.Column("id", sa.SmallInteger(), autoincrement=False, nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="disabled", nullable=False),
        sa.Column("disabled_reason", sa.Text(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_block_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("phase", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
        sa.UniqueConstraint("key", name=op.f("uq_sources_key")),
    )
    op.create_table(
        "suppliers",
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("years_active", sa.Integer(), nullable=True),
        sa.Column("country", sa.CHAR(length=2), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_suppliers")),
        sa.UniqueConstraint(
            "platform", "external_id", name=op.f("uq_suppliers_platform_external_id")
        ),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clerk_user_id", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("clerk_user_id", name=op.f("uq_users_clerk_user_id")),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspaces")),
    )
    op.create_table(
        "collector_runs",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column("slot_key", sa.String(length=30), nullable=True),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="running", nullable=False),
        sa.Column("complete", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rows_fetched", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rows_inserted", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rows_updated", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("rows_unchanged", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("http_requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_status_code", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_collector_runs_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collector_runs")),
    )
    op.create_index(
        op.f("ix_collector_runs_source_id_started_at"),
        "collector_runs",
        ["source_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "uq_collector_runs_successful_slot",
        "collector_runs",
        ["source_id", "slot_key"],
        unique=True,
        postgresql_where=sa.text("status = 'success' AND trigger IN ('schedule', 'catchup')"),
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("category_source", sa.String(length=20), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("main_image_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("merged_into_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], name=op.f("fk_products_category_id_categories")
        ),
        sa.ForeignKeyConstraint(
            ["main_image_id"],
            ["images.id"],
            name=op.f("fk_products_main_image_id_images"),
            use_alter=True,
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["products.id"], name=op.f("fk_products_merged_into_id_products")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
    )
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_index(
        op.f("ix_products_merged_into_id"), "products", ["merged_into_id"], unique=False
    )
    op.create_table(
        "settings",
        sa.Column("default_country", sa.CHAR(length=2), server_default="US", nullable=False),
        sa.Column("currency", sa.CHAR(length=3), server_default="USD", nullable=False),
        sa.Column("payment_fee_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payment_fee_fixed_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("shopify_fee_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("default_cpa_minor", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("target_margin_bps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "default_country = 'US' AND currency = 'USD'", name=op.f("ck_settings_v1_market")
        ),
        sa.CheckConstraint(
            "payment_fee_bps BETWEEN 0 AND 10000", name=op.f("ck_settings_payment_fee_range")
        ),
        sa.CheckConstraint(
            "payment_fee_fixed_minor >= 0 AND default_cpa_minor >= 0",
            name=op.f("ck_settings_cost_range"),
        ),
        sa.CheckConstraint(
            "shopify_fee_bps BETWEEN 0 AND 10000", name=op.f("ck_settings_shopify_fee_range")
        ),
        sa.CheckConstraint(
            "target_margin_bps BETWEEN 0 AND 10000", name=op.f("ck_settings_target_margin_range")
        ),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_settings_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], name=op.f("fk_settings_workspace_id_workspaces")
        ),
        sa.PrimaryKeyConstraint("workspace_id", name=op.f("pk_settings")),
    )
    op.create_index(op.f("ix_settings_workspace_id"), "settings", ["workspace_id"], unique=False)
    op.create_table(
        "stores",
        sa.Column("domain", sa.String(length=253), nullable=False),
        sa.Column("platform", sa.String(length=30), nullable=False),
        sa.Column("shop_id", sa.Text(), nullable=True),
        sa.Column("myshopify_domain", sa.String(length=253), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=True),
        sa.Column("country", sa.CHAR(length=2), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column(
            "exclude_from_labels", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_stores_currency_currencies")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stores")),
        sa.UniqueConstraint("domain", name=op.f("uq_stores_domain")),
    )
    op.create_table(
        "workspace_members",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), server_default="owner", nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_workspace_members_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_members_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("workspace_id", "user_id", name=op.f("pk_workspace_members")),
    )
    op.create_index(
        op.f("ix_workspace_members_user_id"), "workspace_members", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_workspace_members_workspace_id"),
        "workspace_members",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "listings",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("handle", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_norm", sa.Text(), nullable=True),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("product_type", sa.Text(), nullable=True),
        sa.Column("source_tags", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("store_id", sa.BigInteger(), nullable=True),
        sa.Column("supplier_id", sa.BigInteger(), nullable=True),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("match_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.CheckConstraint(
            "num_nonnulls(store_id, supplier_id) <= 1", name=op.f("ck_listings_one_vendor")
        ),
        sa.ForeignKeyConstraint(
            ["product_id"], ["products.id"], name=op.f("fk_listings_product_id_products")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_listings_source_id_sources")
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_listings_store_id_stores")
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name=op.f("fk_listings_supplier_id_suppliers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listings")),
        sa.UniqueConstraint(
            "source_id", "external_id", name=op.f("uq_listings_source_id_external_id")
        ),
    )
    op.create_index(op.f("ix_listings_product_id"), "listings", ["product_id"], unique=False)
    op.create_index(op.f("ix_listings_store_id"), "listings", ["store_id"], unique=False)
    op.create_index(op.f("ix_listings_supplier_id"), "listings", ["supplier_id"], unique=False)
    op.create_table(
        "raw_payloads",
        sa.Column("source_id", sa.SmallInteger(), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=200), nullable=True),
        sa.Column("etag", sa.Text(), nullable=True),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["collector_runs.id"], name=op.f("fk_raw_payloads_run_id_collector_runs")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["sources.id"], name=op.f("fk_raw_payloads_source_id_sources")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_payloads")),
    )
    op.create_index(op.f("ix_raw_payloads_run_id"), "raw_payloads", ["run_id"], unique=False)
    op.create_index(op.f("ix_raw_payloads_sha256"), "raw_payloads", ["sha256"], unique=False)
    op.create_index(
        op.f("ix_raw_payloads_source_id_captured_at"),
        "raw_payloads",
        ["source_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "workspace_tracked_stores",
        sa.Column("store_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_workspace_tracked_stores_store_id_stores")
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_workspace_tracked_stores_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint(
            "workspace_id", "store_id", name=op.f("pk_workspace_tracked_stores")
        ),
    )
    op.create_index(
        op.f("ix_workspace_tracked_stores_store_id"),
        "workspace_tracked_stores",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_tracked_stores_workspace_id"),
        "workspace_tracked_stores",
        ["workspace_id"],
        unique=False,
    )
    op.create_table(
        "fx_rates",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("base", sa.CHAR(length=3), nullable=False),
        sa.Column("quote", sa.CHAR(length=3), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("rate", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["base"], ["currencies.code"], name=op.f("fk_fx_rates_base_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["quote"], ["currencies.code"], name=op.f("fk_fx_rates_quote_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_fx_rates_raw_payload_id_raw_payloads"),
        ),
        sa.PrimaryKeyConstraint("date", "base", "quote", "source", name=op.f("pk_fx_rates")),
        sa.UniqueConstraint(
            "date",
            "base",
            "quote",
            "source",
            "raw_payload_id",
            name=op.f("uq_fx_rates_date_base_quote_source_raw_payload_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_fx_rates_date_captured_at"), "fx_rates", ["date", "captured_at"], unique=False
    )
    op.create_table(
        "images",
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("phash", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_images_listing_id_listings")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_images")),
        sa.UniqueConstraint("listing_id", "url", name=op.f("uq_images_listing_id_url")),
    )
    op.create_index(op.f("ix_images_listing_id"), "images", ["listing_id"], unique=False)
    op.create_table(
        "listing_snapshots",
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("values_hash", sa.String(length=64), nullable=False),
        sa.Column("price_min_minor", sa.BigInteger(), nullable=True),
        sa.Column("price_max_minor", sa.BigInteger(), nullable=True),
        sa.Column("compare_at_min_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=True),
        sa.Column("sold_count", sa.BigInteger(), nullable=True),
        sa.Column("sold_count_raw", sa.Text(), nullable=True),
        sa.Column("orders_window", sa.BigInteger(), nullable=True),
        sa.Column("window_days", sa.Integer(), nullable=True),
        sa.Column("listed_count", sa.BigInteger(), nullable=True),
        sa.Column("rating", sa.Numeric(precision=3, scale=2), nullable=True),
        sa.Column("review_count", sa.BigInteger(), nullable=True),
        sa.Column("rank", sa.BigInteger(), nullable=True),
        sa.Column("rank_kind", sa.String(length=20), nullable=True),
        sa.Column("stock", sa.BigInteger(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_listing_snapshots_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_listing_snapshots_listing_id_listings")
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_listing_snapshots_raw_payload_id_raw_payloads"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listing_snapshots")),
        sa.UniqueConstraint(
            "listing_id",
            "raw_payload_id",
            name=op.f("uq_listing_snapshots_listing_id_raw_payload_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_listing_snapshots_listing_id_captured_at"),
        "listing_snapshots",
        ["listing_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "listing_variants",
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("barcode", sa.Text(), nullable=True),
        sa.Column("option1", sa.Text(), nullable=True),
        sa.Column("option2", sa.Text(), nullable=True),
        sa.Column("option3", sa.Text(), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_listing_variants_listing_id_listings")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_listing_variants")),
        sa.UniqueConstraint(
            "listing_id", "external_id", name=op.f("uq_listing_variants_listing_id_external_id")
        ),
    )
    op.create_index(
        op.f("ix_listing_variants_listing_id"), "listing_variants", ["listing_id"], unique=False
    )
    op.create_table(
        "supplier_offers",
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("moq", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "bulk_tiers",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("warehouse_country", sa.CHAR(length=2), nullable=True),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_supplier_offers_listing_id_listings")
        ),
        sa.PrimaryKeyConstraint("listing_id", name=op.f("pk_supplier_offers")),
    )
    op.create_table(
        "shipping_options",
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("variant_id", sa.BigInteger(), nullable=True),
        sa.Column("origin_country", sa.CHAR(length=2), nullable=True),
        sa.Column("destination_country", sa.CHAR(length=2), nullable=False),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("cost_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("min_days", sa.Integer(), nullable=True),
        sa.Column("max_days", sa.Integer(), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_shipping_options_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["listings.id"], name=op.f("fk_shipping_options_listing_id_listings")
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_shipping_options_raw_payload_id_raw_payloads"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["listing_variants.id"],
            name=op.f("fk_shipping_options_variant_id_listing_variants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shipping_options")),
        sa.UniqueConstraint(
            "listing_id",
            "variant_id",
            "destination_country",
            "method",
            "raw_payload_id",
            name=op.f(
                "uq_shipping_options_listing_id_variant_id_destination_country_method_raw_payload_id"
            ),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_shipping_options_listing_id_captured_at"),
        "shipping_options",
        ["listing_id", "captured_at"],
        unique=False,
    )
    op.create_table(
        "variant_snapshots",
        sa.Column("variant_id", sa.BigInteger(), nullable=False),
        sa.Column("values_hash", sa.String(length=64), nullable=False),
        sa.Column("price_minor", sa.BigInteger(), nullable=True),
        sa.Column("compare_at_minor", sa.BigInteger(), nullable=True),
        sa.Column("currency", sa.CHAR(length=3), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=True),
        sa.Column("inventory_quantity", sa.BigInteger(), nullable=True),
        sa.Column("inventory_management", sa.Text(), nullable=True),
        sa.Column("inventory_policy", sa.Text(), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("observed_for", sa.Date(), nullable=False),
        sa.Column("raw_payload_id", sa.BigInteger(), nullable=False),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.ForeignKeyConstraint(
            ["currency"], ["currencies.code"], name=op.f("fk_variant_snapshots_currency_currencies")
        ),
        sa.ForeignKeyConstraint(
            ["raw_payload_id"],
            ["raw_payloads.id"],
            name=op.f("fk_variant_snapshots_raw_payload_id_raw_payloads"),
        ),
        sa.ForeignKeyConstraint(
            ["variant_id"],
            ["listing_variants.id"],
            name=op.f("fk_variant_snapshots_variant_id_listing_variants"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_variant_snapshots")),
        sa.UniqueConstraint(
            "variant_id",
            "raw_payload_id",
            name=op.f("uq_variant_snapshots_variant_id_raw_payload_id"),
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        op.f("ix_variant_snapshots_variant_id_captured_at"),
        "variant_snapshots",
        ["variant_id", "captured_at"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_products_main_image_id_images", "products", "images", ["main_image_id"], ["id"]
    )
    op.bulk_insert(
        sa.table(
            "currencies", sa.column("code", sa.CHAR(3)), sa.column("exponent", sa.SmallInteger())
        ),
        [
            {"code": "USD", "exponent": 2},
            {"code": "EUR", "exponent": 2},
            {"code": "GBP", "exponent": 2},
            {"code": "CAD", "exponent": 2},
            {"code": "AUD", "exponent": 2},
            {"code": "CNY", "exponent": 2},
            {"code": "JPY", "exponent": 0},
            {"code": "KWD", "exponent": 3},
        ],
    )
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
                "id": 1,
                "key": "shopify_stores",
                "name": "Shopify stores",
                "type": "public_endpoint",
                "enabled": False,
                "phase": 1,
            },
            {
                "id": 2,
                "key": "cj",
                "name": "CJ Dropshipping",
                "type": "official_api",
                "enabled": False,
                "phase": 1,
            },
            {
                "id": 3,
                "key": "google_trends",
                "name": "Google Trends",
                "type": "vendor",
                "enabled": False,
                "phase": 1,
            },
            {
                "id": 4,
                "key": "fx_frankfurter",
                "name": "Frankfurter FX",
                "type": "official_api",
                "enabled": False,
                "phase": 1,
            },
        ],
    )


def downgrade() -> None:
    op.drop_constraint("fk_products_main_image_id_images", "products", type_="foreignkey")
    op.drop_table("variant_snapshots")
    op.drop_table("shipping_options")
    op.drop_table("supplier_offers")
    op.drop_table("listing_variants")
    op.drop_table("listing_snapshots")
    op.drop_table("images")
    op.drop_table("fx_rates")
    op.drop_table("workspace_tracked_stores")
    op.drop_table("raw_payloads")
    op.drop_table("listings")
    op.drop_table("workspace_members")
    op.drop_table("stores")
    op.drop_table("settings")
    op.drop_table("products")
    op.drop_table("collector_runs")
    op.drop_table("workspaces")
    op.drop_table("users")
    op.drop_table("suppliers")
    op.drop_table("sources")
    op.drop_table("currencies")
    op.drop_table("categories")
