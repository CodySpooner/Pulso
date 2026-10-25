import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock
from urllib.parse import parse_qsl

import pytest
from pydantic import SecretStr
from redis import Redis
from sqlalchemy import JSON, Engine, Integer, MetaData, create_engine, event, func, inspect, select
from sqlalchemy import table as sql_table
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session, attributes
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import Source, SourceEvent
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.aliexpress import (
    PRODUCT,
    failure,
    form,
    parse_freight,
    parse_product,
    product_params,
    sign,
)
from pulso_sources.aliexpress import lookup as service
from pulso_sources.framework import Response

FIXTURES = Path(__file__).parent / "fixtures"
AT = datetime(2026, 10, 25, 12, tzinfo=UTC)
PID, SKU = "1005000000000001", "12000000000000001"
# Market and collector tables a lookup could reach; Postgres counts every migrated table.
SQLITE_TABLES = (
    "sources",
    "source_events",
    "collector_runs",
    "collector_run_targets",
    "raw_payloads",
    "suppliers",
    "supplier_offers",
    "listings",
    "listing_snapshots",
    "listing_variants",
    "variant_snapshots",
    "shipping_options",
)


def fixture(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


def error(name: str) -> bytes:
    return json.dumps(json.loads(fixture("errors"))[name]).encode()


class Clock:
    def __init__(self) -> None:
        self.at = AT

    def __call__(self) -> datetime:
        return self.at


class FakeRedis:
    """get/set/incr/expire with real expiry against the test clock."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.data: dict[str, Any] = {}
        self.expiry: dict[str, datetime] = {}
        self.ttls: list[int] = []

    def _live(self, key: str) -> None:
        if key in self.expiry and self.expiry[key] <= self.clock():
            del self.data[key], self.expiry[key]

    def get(self, key: str) -> Any:
        self._live(key)
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value.encode()
        self.expiry.pop(key, None)
        if ex is not None:
            self.ttls.append(ex)
            self.expiry[key] = self.clock() + timedelta(seconds=ex)

    def incr(self, key: str) -> int:
        self._live(key)
        self.data[key] = int(self.data.get(key, 0)) + 1
        return int(self.data[key])

    def expire(self, key: str, seconds: int) -> None:
        self.expiry[key] = self.clock() + timedelta(seconds=seconds)


class Gateway:
    def __init__(self, *answers: Response) -> None:
        self.answers, self.calls = list(answers), list[tuple[str, dict[str, str]]]()

    def __call__(self, method: str, body: bytes) -> Response:
        assert self.answers, "unexpected AliExpress call"
        self.calls.append((method, dict(parse_qsl(body.decode()))))
        return self.answers.pop(0)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "HTTPSConnection", Mock(side_effect=AssertionError("No HTTP")))


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.chdir(tmp_path)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://fixture@localhost/pulso_test")
    monkeypatch.setenv("S3_ACCESS_KEY_ID", "fixture")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "fixture")
    cfg = Settings()
    cfg.aliexpress_enabled = True
    cfg.aliexpress_app_key = "fixture-app-key"
    cfg.aliexpress_app_secret = SecretStr("fixture-app-secret")
    cfg.aliexpress_access_token = SecretStr("fixture-access-token")
    return cfg


def _utc(row: Any, *_: Any) -> None:
    for key in ("disabled_at", "retry_not_before"):
        value = row.__dict__.get(key)
        if value is not None and value.tzinfo is None:
            attributes.set_committed_value(row, key, value.replace(tzinfo=UTC))


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.db)])
def engine(request: pytest.FixtureRequest) -> Iterator[Engine]:
    if request.param == "postgres":
        yield request.getfixturevalue("db_engine")
        return
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    for name in SQLITE_TABLES:
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, JSON) or column.type.__class__.__name__ == "ARRAY":
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(sql_text("'{}'"))
        for constraint in list(table.constraints):
            if isinstance(constraint.name, str) and constraint.name.endswith("one_vendor"):
                table.constraints.remove(constraint)
        table.create(engine)
    event.listen(Source, "load", _utc)
    event.listen(Source, "refresh", _utc)
    try:
        yield engine
    finally:
        event.remove(Source, "load", _utc)
        event.remove(Source, "refresh", _utc)
        engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        session.add(Source(id=99, key="aliexpress", name="AliExpress", type="api", phase=3))
        session.flush()
        session.get_one(Source, 99).enabled = True
        session.commit()
        yield session


def counts(session: Session) -> dict[str, int]:
    count = select(func.count())
    names = inspect(session.get_bind()).get_table_names()
    return {name: session.scalar(count.select_from(sql_table(name))) or 0 for name in names}


def run(session: Session, cache: FakeRedis, settings: Settings, gateway: Gateway, clock: Clock,
        product_id: str = PID, sku_id: str | None = SKU) -> service.Answer:  # fmt: skip
    return service.lookup(
        session, cast(Redis, cache), product_id, sku_id,
        settings=settings, transport=gateway, now=clock,
    )  # fmt: skip


def test_sign_matches_the_documented_worked_examples() -> None:
    # Open Platform "HTTP request sample" (doc 1366, read 2026-10-25), App Secret "helloworld".
    # Keys are listed out of order on purpose: the signature must sort them.
    system = {
        "timestamp": "1517820392000",
        "sign_method": "sha256",
        "code": "3_500102_JxZ05Ux3cnnSSUm6dCxYg6Q26",
        "app_key": "12345678",
    }
    expected = "35607762342831B6A417A0DED84B79C05FEFBF116969C48AD6DC00279A9F4D81"
    assert sign(system, "helloworld", "/auth/token/create") == expected
    assert sign({**system, "sign": "old", "blank": " "}, "helloworld", "/auth/token/create") == (
        expected
    )
    # Case 1 names aliexpress.solution.product.schema.get, but its concatenated string, and so
    # its published signature, carries the method below; the doc is inconsistent, the hash is not.
    business = {
        "timestamp": "1517820392000",
        "sign_method": "sha256",
        "method": "aliexpress.logistics.redefining.getonlinelogisticsinfo",
        "app_key": "123456",
        "aliexpress_category_id": "200135143",
        "access_token": "test",
    }
    assert sign(business, "helloworld") == (
        "F7F7926B67316C9D1E8E15F7E66940ED3059B1638C497D77973F30046EFB5BBB"
    )


def test_form_signs_exactly_the_parameters_it_sends() -> None:
    body = form(
        PRODUCT,
        product_params(PID),
        app_key="fixture-app-key",
        secret="fixture-app-secret",
        access_token="fixture-access-token",
        timestamp_ms=1_761_393_600_000,
    )
    sent = dict(parse_qsl(body.decode()))
    assert sent.pop("sign") == sign(sent, "fixture-app-secret")
    assert b"fixture-app-secret" not in body
    assert sent == {
        "app_key": "fixture-app-key",
        "access_token": "fixture-access-token",
        "format": "json",
        "method": PRODUCT,
        "sign_method": "sha256",
        "timestamp": "1761393600000",
        "product_id": PID,
        "ship_to_country": "US",
        "target_currency": "USD",
        "target_language": "en",
    }


def test_parse_product_and_freight_into_usd_minor_units() -> None:
    product = parse_product(fixture("product"))
    assert product is not None
    assert product.model_dump() == {
        "product_id": PID,
        "title": "Fixture Folding Phone Stand",
        "rating": Decimal("4.7"),
        "review_count": 128,
        "sales": "1000+",
        "store_name": "Fixture Store",
        "skus": [
            {"sku_id": SKU, "price_minor": 549, "sale_price_minor": 399, "currency": "USD",
             "stock": 57},
            {"sku_id": "12000000000000002", "price_minor": 549, "sale_price_minor": 425,
             "currency": "USD", "stock": None},
        ],
    }  # fmt: skip
    simplified = json.loads(fixture("product"))
    dtos = simplified["aliexpress_ds_product_get_response"]["result"]["ae_item_sku_info_dtos"]
    simplified["aliexpress_ds_product_get_response"]["result"]["ae_item_sku_info_dtos"] = dtos[
        "ae_item_sku_info_d_t_o"
    ]
    assert parse_product(json.dumps(simplified).encode()) == product
    assert [(o.code, o.fee_minor, o.free, o.min_days, o.max_days, o.ship_from) for o in
            parse_freight(fixture("freight"))] == [
        ("FIXTURE_STANDARD", 499, False, 9, 15, "CN"),
        ("FIXTURE_ECONOMY", 0, True, 20, 35, "CN"),
    ]  # fmt: skip
    assert parse_product(error("not_found")) is None
    assert parse_freight(error("freight_unavailable")) == []


def test_parse_fails_closed_on_other_currencies_and_a_cents_fee() -> None:
    euro = fixture("product").replace(b'"currency_code": "USD"', b'"currency_code": "EUR"', 1)
    with pytest.raises(ValueError, match="not USD"):
        parse_product(euro)
    cents = fixture("freight").replace(
        b'"shipping_fee_cent": "4.99"', b'"shipping_fee_cent": "499"'
    )
    with pytest.raises(ValueError, match="disagree"):
        parse_freight(cents)


def test_failure_classes() -> None:
    assert failure(200, json.loads(error("throttled"))) == ("blocked", 1)
    assert failure(429, None) == ("blocked", None)
    assert failure(200, json.loads(error("auth_rejected"))) == ("revoked", None)
    assert failure(200, json.loads(error("backend_error"))) == ("failed", None)
    assert failure(503, None) == ("failed", None)
    assert failure(200, json.loads(fixture("product"))) is None


def test_lookup_caches_24h_and_writes_nothing_durable(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    caplog.set_level(logging.DEBUG)
    make_client = Mock()
    monkeypatch.setattr(storage, "make_client", make_client)
    clock = Clock()
    cache = FakeRedis(clock)
    before = counts(session)
    gateway = Gateway(Response(fixture("product"), 200), Response(fixture("freight"), 200))
    first = run(session, cache, settings, gateway, clock)
    assert first.status == "ok" and first.as_of == AT
    assert first.product is not None and first.shipping is not None
    assert (first.product.skus[0].sale_price_minor, first.shipping[0].fee_minor) == (399, 499)
    assert [method for method, _ in gateway.calls] == [PRODUCT, "aliexpress.ds.freight.query"]
    assert counts(session) == before  # raw_payloads, snapshots, listings: no new rows
    assert make_client.call_count == 0  # no S3 client, so no S3 put
    assert cache.ttls == [24 * 3600]
    assert not [r for r in caplog.records if b"Fixture" in r.getMessage().encode()]

    clock.at = AT + timedelta(hours=24) - timedelta(seconds=1)
    assert run(session, cache, settings, gateway, clock) == first
    assert len(gateway.calls) == 2  # inside the TTL: no transport call

    clock.at = AT + timedelta(hours=24)
    gateway.answers += [Response(fixture("product"), 200), Response(fixture("freight"), 200)]
    again = run(session, cache, settings, gateway, clock)
    assert again.status == "ok" and again.as_of == clock.at and len(gateway.calls) == 4
    assert counts(session) == before


def test_consecutive_throttles_disable_once_and_honour_retry_after(
    session: Session, settings: Settings
) -> None:
    clock = Clock()
    cache = FakeRedis(clock)
    throttled = Response(error("throttled"), 200)
    gateway = Gateway(*[throttled] * 4, Response(fixture("product"), 200), *[throttled] * 5)
    statuses = []
    for i in range(10):  # a new product each time, so the one success caches nothing reused
        statuses.append(run(session, cache, settings, gateway, clock, str(100 + i), None).status)
        clock.at += timedelta(seconds=2)  # past the documented 1-second ban
    assert statuses == ["throttled"] * 4 + ["ok"] + ["throttled"] * 4 + ["disabled"]
    source = session.get_one(Source, 99)
    assert (source.enabled, source.status, source.disabled_reason) == (
        False,
        "blocked",
        "consecutive_blocks:aliexpress",
    )
    events = session.scalars(select(SourceEvent).where(SourceEvent.source_id == 99)).all()
    assert [(e.action, e.reason) for e in events] == [("disable", "consecutive_blocks:aliexpress")]
    assert run(session, cache, settings, gateway, clock).status == "disabled"
    assert len(gateway.calls) == 10

    source.enabled, source.status, source.consecutive_block_count = True, "enabled", 0
    session.commit()
    gateway.answers.append(Response(b"", 429, headers={"Retry-After": "120"}))
    assert run(session, cache, settings, gateway, clock, product_id="2").status == "throttled"
    assert source.retry_not_before == clock.at + timedelta(seconds=120)
    clock.at += timedelta(seconds=119)
    assert run(session, cache, settings, gateway, clock, product_id="2").status == "throttled"
    assert len(gateway.calls) == 11  # still inside Retry-After: no call


def test_revoked_auth_disables_at_once_and_errors_do_not_count(
    session: Session, settings: Settings
) -> None:
    clock = Clock()
    cache = FakeRedis(clock)
    gateway = Gateway(Response(error("backend_error"), 200), Response(error("auth_rejected"), 200))
    assert run(session, cache, settings, gateway, clock).status == "error"
    source = session.get_one(Source, 99)
    assert (source.enabled, source.consecutive_block_count) == (True, 0)
    assert run(session, cache, settings, gateway, clock).status == "disabled"
    assert (source.enabled, source.disabled_reason) == (False, "aliexpress_auth_rejected")
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1


def test_off_unconfigured_or_live_guarded_lookups_make_no_call(
    session: Session, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock()
    cache = FakeRedis(clock)
    gateway = Gateway()
    settings.aliexpress_access_token = None
    assert run(session, cache, settings, gateway, clock).status == "not_configured"
    settings.aliexpress_access_token = SecretStr("fixture-access-token")
    settings.aliexpress_enabled = False
    assert run(session, cache, settings, gateway, clock).status == "disabled"
    settings.aliexpress_enabled = True
    # The real transport refuses outside the collector host (AGENTS.md §4).
    answer = service.lookup(session, cast(Redis, cache), PID, settings=settings, now=clock)
    assert answer.status == "disabled"
    monkeypatch.setattr(service, "DAILY_CALL_CAP", 1)
    gateway.answers.append(Response(fixture("product"), 200))
    assert run(session, cache, settings, gateway, clock).status == "throttled"  # freight = call 2
    assert len(gateway.calls) == 1
    with pytest.raises(ValueError, match="digits"):
        run(session, cache, settings, gateway, clock, product_id="1:2")
