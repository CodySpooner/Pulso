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
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    Currency,
    HostHeartbeat,
    Listing,
    ListingSnapshot,
    ListingVariant,
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
        connection.execute(insert(HostHeartbeat).values(host="fixture"))
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


@pytest.mark.parametrize(
    "evidence_sql",
    [
        pytest.param("UPDATE collector_runs SET started_at = NULL, status = 'queued'", id="queued"),
        pytest.param(
            "INSERT INTO listing_snapshots "
            "(listing_id, raw_payload_id, observed_for, values_hash, currency, parser_version) "
            "SELECT :listing, :payload, '2026-10-22', 'fixture', 'USD', version "
            "FROM (VALUES ('1'), ('2')) AS versions(version)",
            id="parser-pair",
        ),
        pytest.param(
            "INSERT INTO search_trends (source_id, raw_payload_id, observed_for, keyword, geo, "
            '"window", granularity, metric, value) '
            "VALUES (1, :payload, '2026-10-22', 'lamp', 'US', 'today 3-m', 'day', 'interest', 40)",
            id="search-trends",
        ),
        pytest.param(
            "INSERT INTO collector_run_targets (run_id, scope, target_id) "
            "VALUES (:run, 'catalog', 'fixture')",
            id="targets",
        ),
        pytest.param(
            "INSERT INTO collection_gaps (source_id, slot_key, slot_start, slot_end, reason) "
            "VALUES (1, 'catalog:2026-10-22', '2026-10-22 00:00Z', '2026-10-23 00:00Z', "
            "'host_offline')",
            id="gaps",
        ),
        pytest.param(
            "INSERT INTO source_events (source_id, action) VALUES (1, 'disable')", id="events"
        ),
        pytest.param(
            "INSERT INTO shipping_options (listing_id, raw_payload_id, observed_for, "
            "destination_country, method, cost_minor, currency, quantity) "
            "VALUES (:listing, :payload, '2026-10-22', 'US', 'standard', 300, 'USD', 3)",
            id="freight-quantity",
        ),
        pytest.param("UPDATE raw_payloads SET template_version = 'csv-v1'", id="import-template"),
        pytest.param("UPDATE sources SET retry_not_before = now() WHERE id = 1", id="retry"),
        pytest.param(
            "INSERT INTO listing_snapshots "
            "(listing_id, raw_payload_id, observed_for, values_hash, currency, parser_version) "
            "VALUES (:listing, :payload, '2026-10-22', 'fixture', 'USD', '2')",
            id="listing-parser",
        ),
        pytest.param(
            "INSERT INTO variant_snapshots "
            "(variant_id, raw_payload_id, observed_for, values_hash, currency, parser_version) "
            "VALUES (:variant, :payload, '2026-10-22', 'fixture', 'USD', '2')",
            id="variant-parser",
        ),
        pytest.param(
            "INSERT INTO shipping_options (listing_id, raw_payload_id, observed_for, "
            "destination_country, method, cost_minor, currency, parser_version) "
            "VALUES (:listing, :payload, '2026-10-22', 'US', 'standard', 100, 'USD', '2')",
            id="freight-parser",
        ),
        pytest.param(
            "INSERT INTO fx_rates "
            "(date, base, quote, rate, source, raw_payload_id, observed_for, parser_version) "
            "VALUES ('2026-10-22', 'USD', 'EUR', 0.9, 'fx_frankfurter', "
            ":payload, '2026-10-22', '2')",
            id="fx-parser",
        ),
    ],
)
def test_phase1_downgrade_refuses_evidence(db_engine: Engine, evidence_sql: str) -> None:
    config = Config(str(Path(__file__).resolve().parents[3] / "alembic.ini"))
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        run_id = connection.scalar(
            insert(CollectorRun)
            .values(source_id=1, trigger="csv", started_at=func.now(), status="success")
            .returning(CollectorRun.id)
        )
        listing_id = connection.scalar(
            insert(Listing)
            .values(source_id=1, external_id="fixture", title="X", url="https://example.test")
            .returning(Listing.id)
        )
        variant_id = connection.scalar(
            insert(ListingVariant)
            .values(listing_id=listing_id, external_id="v1")
            .returning(ListingVariant.id)
        )
        payload_id = connection.scalar(
            insert(RawPayload)
            .values(source_id=1, run_id=run_id, request={}, bytes=0, sha256="0" * 64)
            .returning(RawPayload.id)
        )
        connection.execute(
            text(evidence_sql),
            {"run": run_id, "listing": listing_id, "variant": variant_id, "payload": payload_id},
        )
        with (
            pytest.raises(DBAPIError, match="Phase 1 evidence|started_at.*contains null values"),
            connection.begin_nested(),
        ):
            command.downgrade(config, "0001")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0004"
        assert connection.scalar(text("SELECT to_regclass('source_daily_coverage')")) is not None


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
