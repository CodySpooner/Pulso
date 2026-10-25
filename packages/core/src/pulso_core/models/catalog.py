from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pulso_core.db import Base, BigId, CreatedAt, Observation

# OpenCLIP ViT-B-32 laion2b_s34b_b79k: one 512-d space for images and titles (DEC-237).
EMBEDDING_DIM = 512


def hnsw_cosine(column: str) -> Index:
    return Index(
        None, column, postgresql_using="hnsw", postgresql_ops={column: "vector_cosine_ops"}
    )


def trigram(column: str) -> Index:
    """A pg_trgm GIN index for global search's substring and fuzzy matches (DEC-252)."""
    return Index(None, column, postgresql_using="gin", postgresql_ops={column: "gin_trgm_ops"})


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)


class CategoryMapping(Base):
    __tablename__ = "category_mappings"
    __table_args__ = (
        CheckConstraint("mapping_source IN ('rule', 'ai', 'manual')", name="mapping_source_values"),
    )
    source_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("sources.id"), primary_key=True)
    source_category: Mapped[str] = mapped_column(Text, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    mapping_source: Mapped[str] = mapped_column(String(20))


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (  # Discover's newest sort, scanned backward (DEC-239)
        Index(
            "ix_products_first_seen_at_id",
            "first_seen_at",
            "id",
            postgresql_where=text("merged_into_id IS NULL"),
        ),
        trigram("name"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), index=True)
    category_source: Mapped[str | None] = mapped_column(String(20))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    main_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", use_alter=True))
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    merged_into_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"), index=True)


class Listing(BigId, Base):
    __tablename__ = "listings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        CheckConstraint("num_nonnulls(store_id, supplier_id) <= 1", name="one_vendor"),
        hnsw_cosine("title_embedding"),
        trigram("title"),
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    handle: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    title_norm: Mapped[str | None] = mapped_column(Text)
    # pgvector returns a numpy float32 array.
    title_embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    vendor: Mapped[str | None] = mapped_column(Text)
    product_type: Mapped[str | None] = mapped_column(Text)
    source_tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), index=True)
    product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"), index=True)
    match_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ListingVariant(BigId, Base):
    __tablename__ = "listing_variants"
    __table_args__ = (UniqueConstraint("listing_id", "external_id"),)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    external_id: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str | None] = mapped_column(Text)
    barcode: Mapped[str | None] = mapped_column(Text)
    option1: Mapped[str | None] = mapped_column(Text)
    option2: Mapped[str | None] = mapped_column(Text)
    option3: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    delisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ListingSnapshot(Observation, BigId, Base):
    __tablename__ = "listing_snapshots"
    observation_keys = ("listing_id",)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    values_hash: Mapped[str] = mapped_column(String(64))
    price_min_minor: Mapped[int | None] = mapped_column(BigInteger)
    price_max_minor: Mapped[int | None] = mapped_column(BigInteger)
    compare_at_min_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    available: Mapped[bool | None]
    sold_count: Mapped[int | None] = mapped_column(BigInteger)
    sold_count_raw: Mapped[str | None] = mapped_column(Text)
    orders_window: Mapped[int | None] = mapped_column(BigInteger)
    window_days: Mapped[int | None]
    listed_count: Mapped[int | None] = mapped_column(BigInteger)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    review_count: Mapped[int | None] = mapped_column(BigInteger)
    rank: Mapped[int | None] = mapped_column(BigInteger)
    rank_kind: Mapped[str | None] = mapped_column(String(20))
    stock: Mapped[int | None] = mapped_column(BigInteger)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VariantSnapshot(Observation, BigId, Base):
    __tablename__ = "variant_snapshots"
    observation_keys = ("variant_id",)
    variant_id: Mapped[int] = mapped_column(ForeignKey("listing_variants.id"))
    values_hash: Mapped[str] = mapped_column(String(64))
    price_minor: Mapped[int | None] = mapped_column(BigInteger)
    compare_at_minor: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    available: Mapped[bool | None]
    inventory_quantity: Mapped[int | None] = mapped_column(BigInteger)
    inventory_management: Mapped[str | None] = mapped_column(Text)
    inventory_policy: Mapped[str | None] = mapped_column(Text)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Image(BigId, Base):
    __tablename__ = "images"
    __table_args__ = (UniqueConstraint("listing_id", "url"), hnsw_cosine("embedding"))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int]
    phash: Mapped[int | None] = mapped_column(BigInteger)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIM), nullable=True)


class MatchCandidate(CreatedAt, BigId, Base):
    """One row per listing pair (lower id first); re-scoring updates it, decisions append."""

    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("listing_a_id", "listing_b_id"),
        CheckConstraint("listing_a_id < listing_b_id", name="ordered_pair"),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'merged', 'split')",
            name="status_values",
        ),
        # ponytail: a backward scan serves ORDER BY score DESC (DEC-158 pattern).
        Index(None, "status", "score"),
    )
    listing_a_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    listing_b_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    image_cos: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    title_cos: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    phash_sim: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    price_sane: Mapped[bool | None]
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    scorer_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), server_default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchDecision(BigId, Base):
    """Append-only (DB trigger); one row per listing, so membership(t) replays (R-15)."""

    __tablename__ = "match_decisions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('link', 'unlink', 'merge', 'split', 'accept', 'reject')",
            name="action_values",
        ),
        Index(None, "listing_id", "decided_at"),
    )
    actor: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(20))
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    from_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    to_product_id: Mapped[UUID | None] = mapped_column(ForeignKey("products.id"))
    candidate_id: Mapped[int | None] = mapped_column(ForeignKey("match_candidates.id"))
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductDailyFeature(Base):
    """Point-in-time features; the primary key's prefix indexes (product_id, feature_date)."""

    __tablename__ = "product_daily_features"
    __table_args__ = (CheckConstraint("coverage BETWEEN 0 AND 1", name="coverage_range"),)
    product_id: Mapped[UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    feature_date: Mapped[date] = mapped_column(primary_key=True)
    family: Mapped[str] = mapped_column(String(20), primary_key=True)
    feature_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    velocity_7d: Mapped[float | None] = mapped_column(Double)
    growth_7d: Mapped[float | None] = mapped_column(Double)
    coverage: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    has_gap: Mapped[bool]
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
