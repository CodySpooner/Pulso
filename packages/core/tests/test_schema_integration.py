from datetime import date
from decimal import Decimal
from pathlib import Path

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


def test_migration_roundtrip_and_metadata(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    with db_engine.begin() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
        assert schema.startswith("test_")
        assert connection.scalar(text("SELECT current_schemas(false)")) == [schema]
        assert connection.scalar(
            text("SELECT to_regclass('alembic_version') = to_regclass(:qualified)"),
            {"qualified": f"{schema}.alembic_version"},
        )
        config.attributes["connection"] = connection
        assert (
            compare_metadata(
                MigrationContext.configure(connection, opts={"compare_server_default": True}),
                Base.metadata,
            )
            == []
        )
        command.downgrade(config, "0001")
        command.upgrade(config, "head")
        assert (
            compare_metadata(
                MigrationContext.configure(connection, opts={"compare_server_default": True}),
                Base.metadata,
            )
            == []
        )
        command.downgrade(config, "base")
        command.upgrade(config, "head")
    with Session(db_engine) as session:
        currencies = {
            code: exponent
            for code, exponent in session.execute(select(Currency.code, Currency.exponent))
        }
        assert currencies == CURRENCY_EXPONENTS
        assert session.scalar(select(func.count()).select_from(Source).where(Source.enabled)) == 0
        backup = session.scalar(select(Source).where(Source.key == "backup"))
        assert backup is not None and not backup.enabled


def test_connected_database_is_a_test_database(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        database = connection.scalar(text("SELECT current_database()"))
        assert database == "pulso_ci" or database.startswith("pulso_test")


def test_phase1_upgrade_preserves_legacy_observations(db_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001")
        run = connection.execute(
            insert(CollectorRun)
            .values(source_id=1, trigger="csv")
            .returning(CollectorRun.id, CollectorRun.started_at)
        ).one()
        listing_id = connection.scalar(
            insert(Listing)
            .values(
                source_id=1, external_id="legacy", title="Legacy", url="https://example.test/legacy"
            )
            .returning(Listing.id)
        )
        payload_id = connection.scalar(
            insert(RawPayload)
            .values(source_id=1, run_id=run.id, request={}, bytes=0, sha256="0" * 64)
            .returning(RawPayload.id)
        )
        snapshot_id = connection.scalar(
            insert(ListingSnapshot)
            .values(
                listing_id=listing_id,
                raw_payload_id=payload_id,
                observed_for=date(2026, 10, 22),
                captured_at=run.started_at,
                values_hash="a" * 64,
                price_min_minor=123,
                currency="USD",
            )
            .returning(ListingSnapshot.id)
        )
        command.upgrade(config, "head")
        snapshot = connection.execute(select(ListingSnapshot.__table__)).one()
        assert (
            snapshot.id,
            snapshot.raw_payload_id,
            snapshot.captured_at,
            snapshot.price_min_minor,
            snapshot.parser_version,
        ) == (snapshot_id, payload_id, run.started_at, 123, "1")
        assert connection.scalar(select(CollectorRun.queued_at)) == run.started_at
        command.downgrade(config, "0001")
        command.upgrade(config, "head")
        assert connection.scalar(select(ListingSnapshot.id)) == snapshot_id


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
