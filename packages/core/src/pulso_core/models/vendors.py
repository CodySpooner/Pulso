from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    BigInteger,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from pulso_core.db import Base, BigId, Observation


class Supplier(BigId, Base):
    __tablename__ = "suppliers"
    __table_args__ = (UniqueConstraint("platform", "external_id"),)
    platform: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    years_active: Mapped[int | None]
    country: Mapped[str | None] = mapped_column(CHAR(2))


class SupplierOffer(Base):
    __tablename__ = "supplier_offers"
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), primary_key=True)
    moq: Mapped[int] = mapped_column(server_default="1")
    bulk_tiers: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, server_default=text("'[]'::jsonb")
    )
    warehouse_country: Mapped[str | None] = mapped_column(CHAR(2))


class ShippingOption(Observation, BigId, Base):
    __tablename__ = "shipping_options"
    observation_keys = ("listing_id", "variant_id", "destination_country", "method")
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"))
    variant_id: Mapped[int | None] = mapped_column(ForeignKey("listing_variants.id"))
    origin_country: Mapped[str | None] = mapped_column(CHAR(2))
    destination_country: Mapped[str] = mapped_column(CHAR(2))
    method: Mapped[str] = mapped_column(Text)
    cost_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    min_days: Mapped[int | None]
    max_days: Mapped[int | None]


class Store(BigId, Base):
    __tablename__ = "stores"
    domain: Mapped[str] = mapped_column(String(253), unique=True)
    platform: Mapped[str] = mapped_column(String(30))
    shop_id: Mapped[str | None] = mapped_column(Text)
    myshopify_domain: Mapped[str | None] = mapped_column(String(253))
    currency: Mapped[str | None] = mapped_column(CHAR(3), ForeignKey("currencies.code"))
    country: Mapped[str | None] = mapped_column(CHAR(2))
    status: Mapped[str] = mapped_column(String(20), server_default="active")
    exclude_from_labels: Mapped[bool] = mapped_column(server_default=text("false"))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
