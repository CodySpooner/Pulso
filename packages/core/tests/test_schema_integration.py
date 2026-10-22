from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    Currency,
    Listing,
    ListingSnapshot,
    RawPayload,
    ShippingOption,
    Source,
)
from pulso_core.money import CURRENCY_EXPONENTS

pytestmark = pytest.mark.db


def test_migration_roundtrip_and_metadata(db_engine: Engine) -> None:
    config = Config("alembic.ini")
    with db_engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        assert schema.startswith("test_")
        assert connection.scalar(text("SELECT current_schemas(false)")) == [schema]
        assert connection.scalar(
            text("SELECT to_regclass('alembic_version') = to_regclass(:qualified)"),
            {"qualified": f"{schema}.alembic_version"},
        )
        config.attributes["connection"] = connection
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    with Session(db_engine) as session:
        currencies = {
            code: exponent
            for code, exponent in session.execute(select(Currency.code, Currency.exponent))
        }
        assert currencies == CURRENCY_EXPONENTS
        assert session.scalar(select(func.count()).select_from(Source).where(Source.enabled)) == 0


def test_reparse_payload_does_not_duplicate_observations(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        run = CollectorRun(source_id=1, trigger="csv")
        listing = Listing(
            source_id=1, external_id="fixture-1", url="https://example.test/1", title="Fixture"
        )
        session.add_all([run, listing])
        session.flush()
        payload = RawPayload(source_id=1, run_id=run.id, request={}, bytes=2, sha256="0" * 64)
        session.add(payload)
        session.flush()
        statement = (
            insert(ListingSnapshot)
            .values(
                listing_id=listing.id,
                raw_payload_id=payload.id,
                observed_for=date(2026, 10, 22),
                values_hash="1" * 64,
                price_min_minor=123,
                currency="USD",
                rating=Decimal("4.5"),
            )
            .on_conflict_do_nothing()
            .returning(ListingSnapshot.id)
        )
        assert session.scalar(statement) is not None
        assert session.scalar(statement) is None
        assert session.scalar(select(func.count()).select_from(ListingSnapshot)) == 1
        for method in ("standard", "express"):
            quote = (
                insert(ShippingOption)
                .values(
                    listing_id=listing.id,
                    variant_id=None,
                    destination_country="US",
                    method=method,
                    raw_payload_id=payload.id,
                    observed_for=date(2026, 10, 22),
                    cost_minor=100,
                    currency="USD",
                )
                .on_conflict_do_nothing()
                .returning(ShippingOption.id)
            )
            assert session.scalar(quote) is not None
            assert session.scalar(quote) is None
        assert session.scalar(select(func.count()).select_from(ShippingOption)) == 2
