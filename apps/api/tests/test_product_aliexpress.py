"""GET/POST /v1/products/{id}/aliexpress (AE-3, DEC-289): a fake cache and gateway, no network."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, inspect, select, update
from sqlalchemy import table as sql_table
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers import product_aliexpress as router
from pulso_core.models import Product, Source
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.aliexpress import lookup as service
from pulso_sources.framework import Response

FIXTURES = Path(__file__).parents[3] / "packages/sources/tests/aliexpress/fixtures"
PID, SKU = "1005000000000001", "12000000000000001"
LINK = f"https://www.aliexpress.com/item/{PID}.html?spm=a2g0o.detail&skuId={SKU}"


def fixture(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


def error(name: str) -> bytes:
    return json.dumps(json.loads(fixture("errors"))[name]).encode()


class FakeRedis:
    """get/set/incr/expire with real expiry against a clock the test can move (p3-03's fake)."""

    def __init__(self) -> None:
        self.shift = timedelta(0)
        self.data: dict[str, Any] = {}
        self.expiry: dict[str, datetime] = {}

    @property
    def now(self) -> datetime:
        return datetime.now(UTC) + self.shift

    def move_to(self, at: datetime) -> None:
        self.shift = at - datetime.now(UTC)

    def _live(self, key: str) -> None:
        if key in self.expiry and self.expiry[key] <= self.now:
            del self.data[key], self.expiry[key]

    def get(self, key: str) -> Any:
        self._live(key)
        return self.data.get(key)

    def set(
        self, key: str, value: str, ex: int | None = None, exat: datetime | None = None
    ) -> None:
        self.data[key] = value.encode()
        self.expiry.pop(key, None)
        if ex is not None:
            self.expiry[key] = self.now + timedelta(seconds=ex)
        if exat is not None:
            self.expiry[key] = exat

    def incr(self, key: str) -> int:
        self._live(key)
        self.data[key] = int(self.data.get(key, 0)) + 1
        return int(self.data[key])

    def expire(self, key: str, seconds: int) -> None:
        self.expiry[key] = self.now + timedelta(seconds=seconds)


class Gateway:
    def __init__(self, *answers: Response) -> None:
        self.answers, self.calls = list(answers), list[str]()

    def __call__(self, method: str, body: bytes) -> Response:
        assert self.answers, "unexpected AliExpress call"
        self.calls.append(method)
        return self.answers.pop(0)


def ok_gateway() -> Gateway:
    return Gateway(Response(fixture("product"), 200), Response(fixture("freight"), 200))


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "HTTPSConnection", Mock(side_effect=AssertionError("No HTTP")))


@pytest.fixture
def on(settings: Settings) -> Settings:
    settings.aliexpress_enabled = True
    settings.aliexpress_app_key = "fixture-app-key"
    settings.aliexpress_app_secret = SecretStr("fixture-app-secret")
    settings.aliexpress_access_token = SecretStr("fixture-access-token")
    return settings


@pytest.fixture
def cache() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def api(client: TestClient, db_engine: Engine, cache: FakeRedis) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[router.get_cache] = lambda: cache
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), WORKSPACE)
    return client


WORKSPACE = uuid4()


def make_product(db_engine: Engine, name: str = "Folding phone stand") -> UUID:
    with Session(db_engine) as session:
        row = Product(name=name)
        session.add(row)
        session.commit()
        return row.id


@pytest.fixture
def product(db_engine: Engine) -> UUID:
    return make_product(db_engine)


def source(db_engine: Engine, **values: Any) -> None:
    with Session(db_engine) as session:
        session.execute(update(Source).where(Source.key == "aliexpress").values(**values))
        session.commit()


def transport(api: TestClient, gateway: Gateway | None) -> Gateway | None:
    assert isinstance(api.app, FastAPI)
    if gateway is None:
        api.app.dependency_overrides.pop(router.get_transport, None)
    else:
        api.app.dependency_overrides[router.get_transport] = lambda: gateway
    return gateway


def read(api: TestClient, product: UUID) -> dict[str, Any]:
    response = api.get(f"/v1/products/{product}/aliexpress")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def look_up(api: TestClient, product: UUID, link: str = LINK) -> dict[str, Any]:
    response = api.post(f"/v1/products/{product}/aliexpress", json={"link": link})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body: dict[str, Any] = response.json()
    return body


def counts(session: Session) -> dict[str, int]:
    """Every table's row count (p3-03's helper)."""
    count = select(func.count())
    names = inspect(session.get_bind()).get_table_names()
    return {name: session.scalar(count.select_from(sql_table(name))) or 0 for name in names}


def test_aliexpress_requires_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}/aliexpress").status_code == 401
    assert client.post(f"/v1/products/{uuid4()}/aliexpress", json={"link": PID}).status_code == 401


@pytest.mark.parametrize(
    ("link", "ids"),
    [
        (PID, (PID, None)),
        (f"  {PID}\n", (PID, None)),
        (LINK, (PID, SKU)),
        (f"https://de.aliexpress.com/item/{PID}.html#reviews", (PID, None)),
        (f"https://www.aliexpress.us/item/{PID}.html?skuId=x1", (PID, None)),
        (f"https://www.aliexpress.com.evil.example/item/{PID}.html", None),
        (f"https://example.com/item/{PID}.html", None),
        ("https://www.aliexpress.com/store/1234", None),
        ("١٠٠٥", None),  # non-ASCII digits never reach lookup()
        ("", None),
    ],
)
def test_links_parse_to_product_and_sku_ids(link: str, ids: tuple[str, str | None] | None) -> None:
    assert router.parse_link(link) == ids


def test_unknown_products_and_bad_links_are_refused(api: TestClient, product: UUID) -> None:
    assert api.get(f"/v1/products/{uuid4()}/aliexpress").status_code == 404
    assert api.post(f"/v1/products/{uuid4()}/aliexpress", json={"link": PID}).status_code == 404
    bad = api.post(f"/v1/products/{product}/aliexpress", json={"link": "https://example.com/x"})
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_link")
    nul = api.post(f"/v1/products/{product}/aliexpress", json={"link": f"{PID}\x00"})  # DEC-287
    assert [(e["loc"], e["type"]) for e in nul.json()["errors"]] == [
        (["body", "link"], "string_pattern_mismatch")
    ]


@pytest.mark.parametrize(
    ("change", "status"),
    [
        ({"aliexpress_enabled": False}, "disabled"),
        ({"aliexpress_access_token": None}, "not_configured"),
        ({"row": {"enabled": False}}, "disabled"),  # the seeded row stays off until the owner acts
        ({"transport": None}, "disabled"),  # the collector-host guard: COLLECTORS_LIVE is off
        ({}, "empty"),
    ],
)
def test_each_gate_answers_a_status_and_calls_nothing(
    api: TestClient, on: Settings, db_engine: Engine, product: UUID, change: dict[str, Any],
    status: str,
) -> None:  # fmt: skip
    change = dict(change)
    source(db_engine, **change.pop("row", {"enabled": True}))
    gateway = transport(api, change.pop("transport", Gateway()))
    for name, value in change.items():
        setattr(on, name, value)
    assert read(api, product) == {"status": status, "product": None, "shipping": None,
                                  "as_of": None, "expires_at": None, "retry_at": None}  # fmt: skip
    if status != "empty":
        assert look_up(api, product)["status"] == status
    assert gateway is None or gateway.calls == []


def test_throttles_answer_their_retry_time(
    api: TestClient, on: Settings, db_engine: Engine, cache: FakeRedis, product: UUID
) -> None:
    retry = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=5)
    source(db_engine, enabled=True, retry_not_before=retry)
    transport(api, Gateway())
    assert read(api, product)["status"] == "throttled"
    assert datetime.fromisoformat(read(api, product)["retry_at"]) == retry
    assert look_up(api, product)["status"] == "throttled"

    source(db_engine, retry_not_before=None)  # AliExpress answers 429 with Retry-After
    transport(api, Gateway(Response(b"{}", 429, None, headers={"Retry-After": "120"})))
    answer = look_up(api, product)
    assert (answer["status"], answer["product"]) == ("throttled", None)
    assert datetime.fromisoformat(answer["retry_at"]) > datetime.now(UTC) + timedelta(seconds=100)

    source(db_engine, retry_not_before=None, consecutive_block_count=0)
    day = datetime.now(UTC).date()
    cache.data[f"pulso:aliexpress:calls:{day.isoformat()}"] = service.DAILY_CALL_CAP
    midnight = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)
    assert datetime.fromisoformat(read(api, product)["retry_at"]) == midnight


def test_rows_show_until_the_cache_expires_then_vanish_with_the_source_off(
    api: TestClient, on: Settings, db_engine: Engine, cache: FakeRedis, product: UUID
) -> None:
    """AE-3 verify: nothing outlives the 24 h cache, so with the source off the rows are gone."""
    source(db_engine, enabled=True)
    gateway = transport(api, ok_gateway())
    answer = look_up(api, product)
    assert answer["status"] == "ok"
    assert [s["sku_id"] for s in answer["product"]["skus"]] == [SKU, "12000000000000002"]
    assert answer["shipping"][0]["fee_minor"] == 499
    as_of = datetime.fromisoformat(answer["as_of"])
    assert datetime.fromisoformat(answer["expires_at"]) == as_of + timedelta(hours=24)
    assert read(api, product) == answer  # under the Pulso product's key: no AliExpress id stored

    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    assert read(api, product)["status"] == "empty"  # another workspace's lookup stays its own
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), WORKSPACE)

    source(db_engine, enabled=False)  # the owner turns the source off
    cache.move_to(as_of + timedelta(hours=24) - timedelta(seconds=2))
    assert read(api, product) == answer  # still inside the 24 h the terms allow
    cache.move_to(as_of + timedelta(hours=24) + timedelta(seconds=1))
    assert read(api, product) == {"status": "disabled", "product": None, "shipping": None,
                                  "as_of": None, "expires_at": None, "retry_at": None}  # fmt: skip
    assert gateway is not None and len(gateway.calls) == 2  # nothing refilled it

    cache.shift = timedelta(0)
    source(db_engine, enabled=True)
    transport(api, ok_gateway())
    look_up(api, product, PID)
    assert read(api, product)["status"] == "ok"
    on.aliexpress_enabled = False  # the flag hides even a fresh answer
    assert read(api, product)["status"] == "disabled"


def test_a_cached_answer_keeps_its_own_expiry_and_not_found_is_kept(
    api: TestClient, on: Settings, db_engine: Engine, cache: FakeRedis, product: UUID
) -> None:
    source(db_engine, enabled=True)
    transport(api, ok_gateway())
    first = look_up(api, product)
    as_of = datetime.fromisoformat(first["as_of"])
    second = make_product(db_engine, "Same stand, another listing")
    cache.move_to(as_of + timedelta(hours=20))
    later = look_up(api, second)  # lookup()'s own cache answers, with the first as_of
    assert (later["as_of"], later["expires_at"]) == (first["as_of"], first["expires_at"])
    cache.move_to(as_of + timedelta(hours=24, seconds=1))
    assert read(api, second)["status"] == "empty"

    cache.shift = timedelta(0)
    transport(api, Gateway(Response(error("not_found"), 200)))
    missing = look_up(api, product, "1005000000000009")
    assert (missing["status"], missing["product"]) == ("not_found", None)
    assert read(api, product)["status"] == "not_found"


def test_a_lookup_through_the_endpoint_writes_nothing_durable(
    api: TestClient, on: Settings, db_engine: Engine, product: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    make_client = Mock()
    monkeypatch.setattr(storage, "make_client", make_client)
    source(db_engine, enabled=True)
    transport(api, ok_gateway())
    with Session(db_engine) as session:
        before = counts(session)
    assert look_up(api, product)["status"] == "ok"
    assert read(api, product)["status"] == "ok"
    with Session(db_engine) as session:
        assert counts(session) == before  # every migrated table, raw_payloads included
    assert make_client.call_count == 0  # no S3 client, so no S3 put
