import io
from collections.abc import Iterator, Sequence
from datetime import UTC, date
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from sqlalchemy import JSON, Integer, MetaData, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import RawPayload, SearchTrend, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import Request, Response, UpsertStats, append_observation
from pulso_sources.imports import ADAPTERS, TEMPLATES, ImportData, Row

# Test-only valid rows covering every template column; downloads are header-only (DEC-191).
SAMPLE_ROWS = {
    "shopify_stores": {
        "store_domain": "example.com",
        "product_url": "https://example.com/products/example",
        "title": "Example only",
        "price": "19.99",
        "currency": "USD",
        "compare_at_price": "24.99",
        "available": "true",
        "variant_title": "Example variant",
        "sku": "EXAMPLE",
        "observed_for": "2026-01-01",
    },
    "cj": {
        "cj_product_id": "EXAMPLE-ID",
        "sku": "EXAMPLE-SKU",
        "name": "Example only",
        "unit_cost": "5.00",
        "currency": "USD",
        "warehouse_country": "US",
        "ship_cost_us": "3.00",
        "min_days": "3",
        "max_days": "7",
        "moq": "1",
        "observed_for": "2026-01-01",
    },
    "google_trends": {
        "keyword": "example keyword",
        "date": "2026-01-01",
        "interest": "50",
        "geo": "US",
        "source": "manual",
    },
    "fx_frankfurter": {"date": "2026-01-01", "base": "USD", "quote": "JPY", "rate": "150"},
}


def sample_csv(key: str) -> bytes:
    """Template header plus one explicit valid test row."""
    columns = list(TEMPLATES[key].columns)
    values = [SAMPLE_ROWS[key][name] for name in columns]
    return f"{','.join(columns)}\r\n{','.join(values)}\r\n".encode()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://fixture@localhost/pulso_test",
        s3_access_key_id="fixture",
        s3_secret_access_key="fixture",
    )


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.db)])
def session(request: pytest.FixtureRequest) -> Iterator[Session]:
    if request.param == "postgres":
        with Session(request.getfixturevalue("db_engine"), expire_on_commit=False) as connected:
            yield connected
        return
    # SQLite runs the real lifecycle offline; Postgres owns locking/FKs/UTC guarantees.
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in [
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "search_trends",
    ]:
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSONB):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)
    try:
        with Session(engine, expire_on_commit=False) as offline:
            for i, key in enumerate(TEMPLATES, 1):
                offline.add(Source(id=i, key=key, name=key, type="csv", phase=1))
            offline.commit()
            yield offline
    finally:
        engine.dispose()


class FakeAdapter:
    def __init__(self, data: ImportData, parser_version: str = "1") -> None:
        self.data, self.parser_version = data, parser_version

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise AssertionError("No network in import tests")

    def parse(self, body: bytes) -> Sequence[Row]:
        if self.data.csv is not None:
            return self.data.csv.rows
        import json

        rows: list[Row] = json.loads(body)["products"]
        return rows

    def upsert(
        self, session: Session, records: Sequence[Row], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        inserted = 0
        for row in records:
            observed = row.get("date", row.get("observed_for", self.data.observed_for))
            observed = observed or payload.captured_at.date()
            assert isinstance(observed, date)
            observation = SearchTrend(
                source_id=payload.source_id,
                keyword=str(row.get("keyword", "fixture")),
                geo="US",
                window="import",
                granularity="day",
                metric="interest",
                value=Decimal(parser_version),
                captured_at=payload.captured_at.replace(tzinfo=UTC),
                observed_for=observed,
                raw_payload_id=payload.id,
                parser_version=parser_version,
            )
            inserted += append_observation(session, observation)
        return UpsertStats(inserted=inserted, unchanged=len(records) - inserted)


@pytest.fixture(autouse=True)
def adapters(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in TEMPLATES:
        monkeypatch.setitem(ADAPTERS, key, FakeAdapter)


@pytest.fixture
def s3(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> MagicMock:
    client = MagicMock()
    objects: dict[str, bytes] = {}

    def put(**kwargs: Any) -> None:
        objects[kwargs["Key"]] = kwargs["Body"]

    client.put_object.side_effect = put
    client.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: client)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    return client
