from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    ARRAY,
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from pulso_core.db import Base, BigId, Observation


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(Text)


class Product(Base):
    __tablename__ = "products"
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
    )
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    handle: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    title_norm: Mapped[str | None] = mapped_column(Text)
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
    __table_args__ = (UniqueConstraint("listing_id", "url"),)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int]
    phash: Mapped[int | None] = mapped_column(BigInteger)
