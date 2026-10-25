"""Global search (UX-9, DEC-252): grouping, ranking, merged products, bounds and speed."""

import os
import statistics
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import Listing, Product, ProductDailyFeature, Source, Store, Supplier

NOW = datetime.now(UTC)


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


def search(api: TestClient, q: str, **params: Any) -> dict[str, Any]:
    response = api.get("/v1/search", params={"q": q, **params})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def source_id(session: Session, key: str) -> int:
    return session.scalars(select(Source.id).where(Source.key == key)).one()


def product(session: Session, name: str, growth: float | None = None, **values: Any) -> Product:
    row = Product(name=name, **values)
    session.add(row)
    session.flush()
    if growth is not None:
        session.add(
            ProductDailyFeature(
                product_id=row.id,
                feature_date=NOW.date() - timedelta(days=1),
                family="shp_bump",
                feature_version="1",
                velocity_7d=10,
                growth_7d=growth,
                coverage=1,
                has_gap=False,
            )
        )
    return row


def listing(session: Session, product: Product, source: int, title: str, **vendor: Any) -> None:
    session.add(
        Listing(
            source_id=source,
            external_id=uuid4().hex,
            url="https://example.test/p",
            title=title,
            product_id=product.id,
            **vendor,
        )
    )
    session.flush()


def test_search_requires_a_session(client: TestClient) -> None:
    assert client.get("/v1/search", params={"q": "lamp"}).status_code == 401


@pytest.fixture
def catalog(db_engine: Engine) -> dict[str, Any]:
    """A store, a supplier and products that cover each group and each kind of match."""
    with Session(db_engine) as session:
        shopify, cj = source_id(session, "shopify_stores"), source_id(session, "cj")
        session.get_one(Source, shopify).config = {"expected_interval": 86_400}
        store = Store(
            domain="glowbeam.example.test",
            myshopify_domain="glowbeam-dev.myshopify.com",
            platform="shopify",
            last_crawled_at=NOW - timedelta(days=3),  # past 2x the daily interval
        )
        fresh = Store(domain="quietdesk.example.test", platform="shopify")  # never crawled
        supplier = Supplier(platform="cj", external_id="cj-1", name="Shenzhen Glowtech Co.")
        session.add_all([store, fresh, supplier])
        session.flush()
        aurora = product(session, "Aurora lamp", growth=0.2)
        nebula = product(session, "Nebula lamp", growth=0.5)
        listing(session, aurora, shopify, "Aurora lamp", store_id=store.id)
        listing(session, nebula, shopify, "Nebula galaxy projector", store_id=store.id)
        listing(session, aurora, cj, "LED aurora lamp", supplier_id=supplier.id)
        for name in (
            "Adjustable posture corrector",
            "Postrue corrector brace",  # a one-letter typo: only the fuzzy match finds it
            "Posture corrector belt",
            "Posture corrector",
        ):
            product(session, name)
        session.commit()
        return {
            "store": store.id,
            "supplier": supplier.id,
            "aurora": aurora.id,
            "nebula": nebula.id,
        }


@pytest.mark.db
def test_a_store_domain_returns_the_store(api: TestClient, catalog: dict[str, Any]) -> None:
    body = search(api, "glowbeam")
    assert body["products"] == [] and body["suppliers"] == []
    assert body["stores"] == [
        {
            "id": catalog["store"],
            "domain": "glowbeam.example.test",
            "myshopify_domain": "glowbeam-dev.myshopify.com",
            "match": {"field": "domain", "text": "glowbeam.example.test", "kind": "prefix"},
            "last_crawled_at": body["stores"][0]["last_crawled_at"],
            "stale": True,
            "top_product_id": str(catalog["nebula"]),  # the higher 7-day growth
        }
    ]
    assert not body["catalog_empty"]
    by_shop = search(api, "glowbeam-dev")["stores"][0]
    assert by_shop["match"] == {
        "field": "myshopify_domain",
        "text": "glowbeam-dev.myshopify.com",
        "kind": "prefix",
    }
    typo = search(api, "glowbeem")["stores"]
    assert [(s["domain"], s["match"]["kind"]) for s in typo] == [("glowbeam.example.test", "fuzzy")]
    never = search(api, "quietdesk")["stores"][0]
    assert (never["last_crawled_at"], never["stale"], never["top_product_id"]) == (
        None,
        False,
        None,
    )


@pytest.mark.db
def test_a_supplier_name_returns_the_supplier(api: TestClient, catalog: dict[str, Any]) -> None:
    body = search(api, "Shenzhen Glowtech")
    assert body["products"] == [] and body["stores"] == []
    assert body["suppliers"] == [
        {
            "id": catalog["supplier"],
            "name": "Shenzhen Glowtech Co.",
            "platform": "cj",
            "match": {"field": "name", "text": "Shenzhen Glowtech Co.", "kind": "prefix"},
            "top_product_id": str(catalog["aurora"]),
        }
    ]
    both = search(api, "glow")
    assert [len(both[group]) for group in ("products", "stores", "suppliers")] == [0, 1, 1]


@pytest.mark.db
def test_ranking_is_exact_then_prefix_then_substring_then_fuzzy(
    api: TestClient, catalog: dict[str, Any]
) -> None:
    hits = search(api, "  posture CORRECTOR ")["products"]  # trimmed, any case
    assert [(hit["title"], hit["match"]["kind"]) for hit in hits] == [
        ("Posture corrector", "exact"),
        ("Posture corrector belt", "prefix"),
        ("Adjustable posture corrector", "substring"),
        ("Postrue corrector brace", "fuzzy"),
    ]
    assert hits[0]["category"] is None


@pytest.mark.db
def test_a_listing_title_finds_its_product(api: TestClient, catalog: dict[str, Any]) -> None:
    hits = search(api, "galaxy projector")["products"]
    assert [(hit["id"], hit["title"]) for hit in hits] == [(str(catalog["nebula"]), "Nebula lamp")]
    assert hits[0]["match"] == {
        "field": "listing_title",
        "text": "Nebula galaxy projector",
        "kind": "substring",
    }
    # The product's own title and a listing title both match: one hit, the title preferred.
    aurora = search(api, "aurora lamp")["products"]
    assert [(hit["title"], hit["match"]["field"]) for hit in aurora] == [("Aurora lamp", "title")]


@pytest.mark.db
def test_merged_products_resolve_to_the_survivor_once(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        shopify = source_id(session, "shopify_stores")
        survivor = product(session, "Sunrise alarm clock", growth=0.1)
        merged = product(session, "Sunrise alarm clock", merged_into_id=survivor.id, growth=0.9)
        listing(session, merged, shopify, "Sunrise wake-up light")
        store = Store(domain="dawnshop.example.test", platform="shopify")
        session.add(store)
        session.flush()
        listing(session, merged, shopify, "Dawn light", store_id=store.id)
        session.commit()
        ids = (str(survivor.id), str(merged.id))
    for q in ("sunrise", "wake-up light"):
        assert [hit["id"] for hit in search(api, q)["products"]] == [ids[0]], q
    assert search(api, "wake-up light")["products"][0]["title"] == "Sunrise alarm clock"
    assert search(api, "dawnshop")["stores"][0]["top_product_id"] == ids[0]


@pytest.mark.db
def test_each_group_holds_at_most_limit(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        for i in range(25):
            product(session, f"Widget {i:02}")
        session.commit()
    assert len(search(api, "widget")["products"]) == 5
    assert len(search(api, "widget", limit=2)["products"]) == 2
    assert len(search(api, "widget", limit=20)["products"]) == 20
    for limit in (0, 21):
        response = api.get("/v1/search", params={"q": "widget", "limit": limit})
        assert response.status_code == 422


@pytest.mark.db
def test_query_bounds(api: TestClient, catalog: dict[str, Any]) -> None:
    empty = {"products": [], "stores": [], "suppliers": [], "catalog_empty": False}
    for q in ("", "a", "  g  "):  # under 2 characters once trimmed: empty, not an error
        assert search(api, q) == empty
    assert search(api, "%_") == empty  # LIKE wildcards are literal
    assert search(api, f"  {'x' * 100}  ") == empty  # 100 once trimmed
    assert api.get("/v1/search", params={"q": "x" * 101}).status_code == 422
    assert api.get("/v1/search").status_code == 422


@pytest.mark.db
def test_xr32_a_nul_byte_in_the_query_is_a_422_not_a_500(
    api: TestClient, catalog: dict[str, Any]
) -> None:
    response = api.get("/v1/search", params={"q": "ab\x00cd"})  # Postgres text can't hold NUL
    assert response.status_code == 422
    assert search(api, "ab\tcd")["products"] == []  # other control characters still search


@pytest.mark.db
def test_an_empty_catalog_says_so(api: TestClient, db_engine: Engine) -> None:
    assert search(api, "lamp")["catalog_empty"] is True
    with Session(db_engine) as session:
        session.add(Supplier(platform="cj", external_id="cj-1", name="Anything"))
        session.commit()
    assert search(api, "lamp")["catalog_empty"] is False


# UX-9's verify: a store domain or a supplier name returns within 200 ms locally, on a realistic
# catalog. Shared CI runners are slower and noisier, so CI (which sets CI=true) gets 500 ms.
WORDS = (
    "lamp led glow posture corrector mask face sunset projector galaxy aurora massage gun neck "
    "pillow dog bed cat toy bottle blender kitchen knife yoga mat phone stand car organizer "
    "baby monitor hair brush beard trimmer smart watch band"
).split()
SEED = (
    # 10,000 products named from three words, 2,000 stores, 500 suppliers.
    """INSERT INTO products (id, name, first_seen_at)
    SELECT gen_random_uuid(), initcap(w[1 + i % n]) || ' ' || w[1 + i * 7 % n] || ' '
           || w[1 + i * 13 % n] || ' ' || i, now() - i * interval '1 minute'
    FROM generate_series(1, 10000) i, words""",
    """INSERT INTO stores (domain, platform, last_crawled_at)
    SELECT w[1 + i % n] || '-' || w[1 + i * 3 % n] || i || '.example.test', 'shopify',
           now() - interval '6 hours'
    FROM generate_series(1, 2000) i, words""",
    """INSERT INTO suppliers (platform, external_id, name)
    SELECT 'cj', 'cj-' || i, initcap(w[1 + i % n]) || ' ' || w[1 + i * 11 % n]
           || ' Trading Co. ' || i
    FROM generate_series(1, 500) i, words""",
    # Two store listings and one supplier listing per product, and a feature row for each.
    """INSERT INTO listings (source_id, external_id, url, title, product_id, store_id, supplier_id)
    SELECT CASE WHEN k < 2 THEN 1 ELSE 2 END, p.n || '-' || k, 'https://example.test/p',
           p.name || (ARRAY['', ' - free shipping', ' wholesale'])[k + 1], p.id,
           CASE WHEN k < 2 THEN 1 + p.n * (k + 1) % 2000 END, CASE WHEN k = 2 THEN 1 + p.n % 500 END
    FROM (SELECT id, name, row_number() OVER (ORDER BY id) n FROM products) p,
         generate_series(0, 2) k""",
    """INSERT INTO product_daily_features (product_id, feature_date, family, feature_version,
                                        velocity_7d, growth_7d, coverage, has_gap)
    SELECT id, current_date - 1, 'shp_bump', '1', 10, random(), 1, false FROM products""",
)


@pytest.mark.db
def test_search_p95_under_200_ms_on_a_realistic_catalog(api: TestClient, db_engine: Engine) -> None:
    words = f"WITH words AS (SELECT CAST(:words AS text[]) w, {len(WORDS)} n) "
    with db_engine.begin() as connection:
        for sql in SEED:
            connection.execute(text(words + sql if "words" in sql else sql), {"words": WORDS})
        store = connection.execute(text("SELECT domain FROM stores WHERE id = 1234")).scalar_one()
        supplier = connection.execute(
            text("SELECT name FROM suppliers WHERE id = 321")
        ).scalar_one()
    # Steady state: autovacuum flushes a GIN index's pending list after a bulk insert.
    with db_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM ANALYZE products, listings, stores, suppliers"))

    budget = 500 if os.getenv("CI") else 200
    queries = {
        "store domain": store,
        "store prefix": store[:12],
        "supplier name": supplier,
        "supplier word": supplier.split()[0],
        "product words": "posture corrector",
        "typo": "postrue corector",
        "two letters": "la",
    }
    for label, q in queries.items():
        first = search(api, q)
        if label.startswith("store"):
            assert store in [hit["domain"] for hit in first["stores"]], label
        if label == "supplier name":
            assert first["suppliers"][0]["name"] == supplier
        timings = []
        for _ in range(40):
            started = perf_counter()
            search(api, q)
            timings.append((perf_counter() - started) * 1000)
        p95 = statistics.quantiles(timings, n=20)[-1]
        print(f"search {label!r} ({q}): p50 {statistics.median(timings):.1f} ms, p95 {p95:.1f} ms")
        assert p95 < budget, f"{label}: p95 {p95:.1f} ms over {budget} ms"
