import math
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.main import create_app
from pulso_api.routers.products import NO_MARGIN, NO_SIGNAL
from pulso_core.models import (
    Category,
    CollectorRun,
    Image,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    RawPayload,
    Source,
    Store,
    Supplier,
)

STATS = ("store_count", "supplier_count", "price_min_minor", "price_max_minor")
NOW = datetime.now(UTC)


def numbers_without_as_of(spec: dict[str, Any], prefix: str = "/v1/products") -> list[str]:
    """Every schema in a 2xx product response that holds a number but no required `as_of`."""
    schemas = spec["components"]["schemas"]
    found: list[str] = []
    seen: set[str] = set()

    def walk(node: Any, where: str) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, where)
        if not isinstance(node, dict):
            return
        if "$ref" in node:
            name = node["$ref"].rsplit("/", 1)[1]
            if name not in seen:
                seen.add(name)
                walk(schemas[name], name)
            return
        numbers = [
            key
            for key, prop in node.get("properties", {}).items()
            if {"integer", "number"} & {item.get("type") for item in [prop, *prop.get("anyOf", [])]}
        ]
        if numbers and "as_of" not in node.get("required", []):
            found.extend(f"{where}.{key}" for key in numbers)
        for value in node.values():
            walk(value, where)

    for path, operations in spec["paths"].items():
        if path.startswith(prefix):
            for operation in operations.values():
                for status, response in operation["responses"].items():
                    if status.startswith("2"):
                        walk(response, path)
    return found


def test_every_number_in_a_product_resource_carries_as_of() -> None:
    spec = create_app().openapi()
    assert any(path.startswith("/v1/products") for path in spec["paths"])
    assert numbers_without_as_of(spec) == []
    # The check itself catches a bare number (and a Problem's status outside the products prefix).
    assert numbers_without_as_of(spec, "/v1/me") == []
    assert numbers_without_as_of(spec, "/v1/settings") != []


def test_product_requires_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}").status_code == 401
    assert client.get(f"/v1/products/{uuid4()}/overview").status_code == 401


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


def snapshot(
    session: Session, listing: Listing, hours_ago: float, **values: Any
) -> ListingSnapshot:
    run = CollectorRun(source_id=listing.source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=listing.source_id, run_id=run.id, request={}, bytes=1, sha256=uuid4().hex * 2
    )
    session.add(payload)
    session.flush()
    row = ListingSnapshot(
        listing_id=listing.id,
        captured_at=NOW - timedelta(hours=hours_ago),
        observed_for=date(2026, 10, 24),
        raw_payload_id=payload.id,
        values_hash=uuid4().hex,
        currency=values.pop("currency", "USD"),
        **values,
    )
    session.add(row)
    session.flush()
    return row


def listing(session: Session, product: Product, source_id: int, **vendor: Any) -> Listing:
    row = Listing(
        source_id=source_id,
        external_id=uuid4().hex,
        url="https://example.test/p",
        title="Sunset lamp",
        product_id=product.id,
        **vendor,
    )
    session.add(row)
    session.flush()
    return row


@pytest.mark.db
def test_product_header_traces_every_stat(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        session.get_one(Source, 1).config = {"expected_interval": 3600}  # shopify: stale after 2 h
        session.add(Category(id=1, name="Lamps", path="Home & Garden > Lighting > Lamps"))
        stores = [Store(domain=f"s{i}.example.test", platform="shopify") for i in range(2)]
        supplier = Supplier(platform="cj", external_id="CJ1", name="CJ supplier")
        product = Product(name="Sunset lamp", category_id=1)
        session.add_all([*stores, supplier, product])
        session.flush()
        a = listing(session, product, 1, store_id=stores[0].id)
        snapshot(session, a, 30, price_min_minor=1900, price_max_minor=4500)  # superseded
        low = snapshot(session, a, 5, price_min_minor=2400, price_max_minor=3900)
        cad = listing(session, product, 1, store_id=stores[1].id)
        newest_store = snapshot(session, cad, 3, price_min_minor=100, currency="CAD")
        gone = listing(session, product, 1, store_id=stores[1].id, delisted_at=NOW)
        snapshot(session, gone, 1, price_min_minor=50)
        cj = listing(session, product, 2, supplier_id=supplier.id)
        offer = snapshot(session, cj, 1, price_min_minor=800)
        image = Image(listing_id=a.id, url="https://cdn.example.test/lamp.jpg", position=0)
        session.add(image)
        session.flush()
        product.main_image_id = image.id
        session.commit()
        ids = {"product": str(product.id), "low": low.raw_payload_id}
        ids |= {"store": newest_store.raw_payload_id, "offer": offer.raw_payload_id}

    response = api.get(f"/v1/products/{ids['product']}")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Sunset lamp"
    assert body["category"] == "Home & Garden > Lighting > Lamps"
    assert body["image_url"] == "https://cdn.example.test/lamp.jpg"
    assert body["currency"] == "USD"
    for key in STATS:
        assert body[key]["as_of"] and body[key]["source"], key
    assert body["store_count"] | {"as_of": None} == {
        "value": 2,  # the delisted listing doesn't count; the CAD one does
        "source": "shopify_stores",
        "source_name": "Shopify stores",
        "as_of": None,
        "raw_payload_id": ids["store"],
        "method": None,
        "stale": True,
    }
    assert datetime.fromisoformat(body["store_count"]["as_of"]) == NOW - timedelta(hours=3)
    assert body["supplier_count"]["value"] == 1
    assert body["supplier_count"]["source"] == "cj"
    assert body["supplier_count"]["raw_payload_id"] == ids["offer"]
    assert body["supplier_count"]["stale"] is False  # no expected interval configured
    # Prices come from each listing's latest USD snapshot, never a superseded or delisted one.
    assert (body["price_min_minor"]["value"], body["price_max_minor"]["value"]) == (2400, 3900)
    assert body["price_min_minor"]["raw_payload_id"] == ids["low"]
    assert body["price_max_minor"]["raw_payload_id"] == ids["low"]


@pytest.mark.db
def test_a_stat_with_no_source_is_null_with_a_reason(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        product = Product(name="Unmatched")
        session.add(product)
        session.commit()
        product_id = product.id

    body = api.get(f"/v1/products/{product_id}").json()
    assert (body["image_url"], body["category"]) == (None, None)
    for key in STATS:
        assert body[key]["value"] is None
        assert body[key]["reason"].endswith("yet.")
        assert "as_of" not in body[key]


@pytest.mark.db
def test_unknown_product_is_a_404_problem(api: TestClient) -> None:
    response = api.get(f"/v1/products/{uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "not_found"
    assert api.get("/v1/products/not-a-uuid").status_code == 422


@pytest.mark.db
def test_merged_product_redirects_to_the_survivor(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        survivor = Product(name="Survivor")
        session.add(survivor)
        session.flush()
        merged = Product(name="Merged", merged_into_id=survivor.id)
        session.add(merged)
        session.commit()
        ids: tuple[UUID, UUID] = (merged.id, survivor.id)

    url = f"/v1/products/{ids[0]}?tab=profit&supplier=99102"
    response = api.get(url, follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == f"{ids[1]}?tab=profit&supplier=99102"
    assert response.headers["cache-control"] == "no-store"  # a merge can be undone
    followed = api.get(url)
    assert followed.status_code == 200
    assert followed.json()["id"] == str(ids[1])
    assert followed.url.query == b"tab=profit&supplier=99102"


# The Discover feed (UX-2, DEC-239).


def seed_product(
    session: Session,
    name: str,
    days_old: float,
    *,
    stores: tuple[tuple[int, int | None], ...] = (),
    suppliers: int = 0,
    features: tuple[
        tuple[str, int, float, float | None, bool], ...
    ] = (),  # family, days ago, V7, G7, gap
    category_id: int | None = None,
) -> Product:
    product = Product(
        name=name, first_seen_at=NOW - timedelta(days=days_old), category_id=category_id
    )
    session.add(product)
    session.flush()
    for low, high in stores:
        store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
        session.add(store)
        session.flush()
        row = listing(session, product, 1, store_id=store.id)
        snapshot(session, row, 6, price_min_minor=low, price_max_minor=high)
    for _ in range(suppliers):
        supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
        session.add(supplier)
        session.flush()
        snapshot(
            session, listing(session, product, 2, supplier_id=supplier.id), 9, price_min_minor=800
        )
    for family, days_ago, v7, growth, gap in features:
        session.add(
            ProductDailyFeature(
                product_id=product.id,
                feature_date=(NOW - timedelta(days=days_ago)).date(),
                family=family,
                feature_version="1",
                velocity_7d=v7,
                growth_7d=growth,
                coverage=1,
                has_gap=gap,
            )
        )
    session.flush()
    return product


def g7(v7: float, v7_prev: float) -> float:
    """Velocity & Acceleration step 3 with k = 5: what the feature job stores as growth_7d."""
    return math.log((v7 + 5) / (v7_prev + 5))


@pytest.fixture
def feed(api: TestClient, db_engine: Engine) -> dict[str, str]:
    with Session(db_engine) as session:
        session.add(Category(id=7, name="Lamps", path="Home & Garden > Lighting > Lamps"))
        session.flush()
        products = {
            # 1 → 3 units/7d is +200% raw but G7 0.288; 20 → 35 is +75% raw but G7 0.470.
            "small_base": seed_product(
                session,
                "Small base",
                1,
                stores=((2400, 3900),),
                features=(("shp_bump", 1, 3, g7(3, 1), False),),
            ),
            "steady": seed_product(
                session,
                "Steady",
                5,
                stores=((1500, None), (2000, 2500)),
                suppliers=1,
                category_id=7,
                features=(
                    ("shp_bump", 1, 35, g7(35, 20), True),
                    ("cj_stock", 1, 90, 2.5, False),  # same day, worse grade
                    ("shp_inv", 3, 50, 3.0, False),  # better grade, older day
                ),
            ),
            "supplier_only": seed_product(
                session,
                "Supplier only",
                40,
                suppliers=2,
                features=(("cj_stock", 2, 12, g7(12, 30), False),),
            ),
            # A gapped window: V7 and G7 NULL, so no family qualifies.
            "no_signal": seed_product(
                session,
                "No signal",
                5,
                stores=((6000, 9000),),
                features=(("shp_bump", 1, 4, None, True),),
            ),
            "old": seed_product(session, "Old", 120, stores=((900, 1200),), category_id=7),
            "unmatched": seed_product(session, "Unmatched", 5),
        }
        session.add(Product(name="Merged", merged_into_id=products["steady"].id, first_seen_at=NOW))
        session.commit()
        return {key: str(product.id) for key, product in products.items()}


def walk(api: TestClient, limit: int = 2, **query: Any) -> list[dict[str, Any]]:
    """Every item of one query, following next_cursor page by page."""
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        params = {**query, "limit": limit} | ({"cursor": cursor} if cursor else {})
        response = api.get("/v1/products", params=params)
        assert response.status_code == 200, response.json()
        body = response.json()
        items += body["items"]
        cursor = body["next_cursor"]
        if cursor is None:
            return items


@pytest.mark.db
def test_every_sort_pages_every_product_exactly_once(api: TestClient, feed: dict[str, str]) -> None:
    names = {value: key for key, value in feed.items()}
    orders = {}
    for sort in ("momentum", "newest", "fewest_sellers"):
        ids = [item["id"] for item in walk(api, sort=sort)]
        assert sorted(ids) == sorted(feed.values()), (
            sort
        )  # the merged product never appears; none twice
        assert ids == [item["id"] for item in walk(api, limit=100, sort=sort)], sort
        orders[sort] = [names[i] for i in ids]
    # Latest day first, then the best grade on it; G7 ranks 20 → 35 above 1 → 3 (raw % would not).
    assert orders["momentum"][:3] == ["steady", "small_base", "supplier_only"]
    assert set(orders["momentum"][3:]) == {
        "no_signal",
        "old",
        "unmatched",
    }  # insufficient signal sinks
    assert orders["newest"][0] == "small_base"
    assert orders["newest"][-2:] == ["supplier_only", "old"]
    stores = {item["id"]: item["store_count"]["value"] or 0 for item in walk(api, limit=100)}
    assert [stores[feed[name]] for name in orders["fewest_sellers"]] == [0, 0, 1, 1, 1, 2]


@pytest.mark.db
def test_each_filter_narrows_the_feed(api: TestClient, feed: dict[str, str]) -> None:
    def names(**query: Any) -> set[str]:
        ids = {item["id"] for item in walk(api, limit=100, **query)}
        return {key for key, value in feed.items() if value in ids}

    assert names() == set(feed)
    assert names(category=7) == {"steady", "old"}
    assert names(price_min=3000) == {"small_base", "no_signal"}  # the band reaches $30
    assert names(price_max=1600) == {"steady", "old"}  # the band starts at or under $16
    assert names(price_min=1300, price_max=2000) == {"steady"}
    assert names(source="cj") == {"steady", "supplier_only"}
    assert names(source="google_trends") == set()
    assert names(first_seen_days=7) == {"small_base", "steady", "no_signal", "unmatched"}
    assert names(first_seen_days=90) == set(feed) - {"old"}
    assert names(has_sellers=True) == {"small_base", "steady", "no_signal", "old"}
    assert names(has_sellers=False) == {"supplier_only", "unmatched"}
    assert names(has_sellers=True, category=7, sort="newest") == {"steady", "old"}


@pytest.mark.db
def test_feed_items_trace_every_number(api: TestClient, feed: dict[str, str]) -> None:
    body = api.get("/v1/products", params={"limit": 100}).json()
    items = {item["id"]: item for item in body["items"]}
    steady = items[feed["steady"]]
    assert steady["velocity"] | {"as_of": None} == {
        "value": 35,
        "source": "shopify_stores",
        "source_name": "Shopify stores",
        "as_of": None,
        "raw_payload_id": None,
        "method": "Shopify updated_at bumps, a lower bound",
        "stale": False,
        "family": "shp_bump",
        "grade": "B",
        "growth": pytest.approx(math.log(40 / 25)),
        "gap": True,
    }
    # A feature day's data ends at the next 00:00Z (DEC-031), or earlier if computed sooner.
    day_end = datetime.combine((NOW - timedelta(days=1)).date() + timedelta(days=1), time(), UTC)
    assert datetime.fromisoformat(steady["velocity"]["as_of"]) <= day_end
    assert (steady["store_count"]["value"], steady["supplier_count"]["value"]) == (2, 1)
    assert (steady["price_min_minor"]["value"], steady["price_max_minor"]["value"]) == (1500, 2500)
    assert steady["category"] == "Home & Garden > Lighting > Lamps"
    # The card's freshness is its oldest feeding family: the CJ snapshot, 9 h ago.
    assert datetime.fromisoformat(steady["as_of"]) == NOW - timedelta(hours=9)
    for each in items.values():
        assert each["best_margin_minor"] == {
            "value": None,
            "reason": "The landed-cost engine arrives with UX-8.",
        }
    for key in ("no_signal", "old", "unmatched"):
        assert items[feed[key]]["velocity"] == {
            "value": None,
            "reason": "No demand family has a 7-day growth yet.",
        }
    assert items[feed["unmatched"]]["as_of"] is None
    assert items[feed["unmatched"]]["store_count"] == {
        "value": None,
        "reason": "No store listing matched yet.",
    }
    # The seeded sources are disabled: both feeding sources say so; Trends feeds nothing.
    assert [(d["source"], d["state"]) for d in body["degraded"]] == [
        ("shopify_stores", "disabled"),
        ("cj", "disabled"),
    ]
    assert datetime.fromisoformat(body["as_of"]) > NOW - timedelta(
        minutes=5
    )  # the newest raw payload


@pytest.mark.db
def test_feed_rejects_bad_queries(api: TestClient, feed: dict[str, str]) -> None:
    for query in (
        {"limit": 101},
        {"limit": 0},
        {"first_seen_days": 14},
        {"sort": "trend"},
        {"price_min": -1},
        {"cursor": "nope"},
        {"cursor": '["x", "y"]'},
        {"sort": "newest", "cursor": "[1, 2]"},
    ):
        assert api.get("/v1/products", params=query).status_code == 422, query


@pytest.mark.db
def test_categories_lists_categories_in_use(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        session.add_all(
            [
                Category(id=1, name="Lamps", path="Home > Lamps"),
                Category(id=2, name="Rugs", path="Home > Rugs"),
            ]
        )
        session.flush()
        session.add(Product(name="Lamp", category_id=1))
        session.commit()
    assert api.get("/v1/categories").json() == [{"id": 1, "path": "Home > Lamps"}]


@pytest.mark.db
def test_newest_pages_scan_the_first_seen_index_backward(
    api: TestClient, db_engine: Engine
) -> None:
    with db_engine.begin() as connection:
        connection.execute(
            text("""
            INSERT INTO products (id, name, first_seen_at, merged_into_id)
            SELECT gen_random_uuid(), 'p' || i, now() - i * interval '1 minute', NULL
            FROM generate_series(1, 20000) i
        """)
        )
        connection.execute(text("ANALYZE products"))
    queries: list[tuple[str, Any]] = []

    def capture(conn: Any, cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        if "ORDER BY" in statement and "anon_1.first_seen_at DESC" in statement:
            queries.append((statement, parameters))

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        first = api.get("/v1/products", params={"sort": "newest"}).json()
        api.get("/v1/products", params={"sort": "newest", "cursor": first["next_cursor"]})
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
    assert len(queries) == 2
    with db_engine.connect() as connection:
        for sql, params in queries:
            plan = connection.exec_driver_sql(
                "EXPLAIN (ANALYZE, FORMAT JSON) " + sql, params
            ).scalar_one()[0]["Plan"]
            # The outer chain down to the products scan: no sort of the feed. A lateral's own few
            # rows (count DISTINCT per product) may sort; those hang off the inner side.
            outer = [plan]
            while outer[-1].get("Plans"):
                outer.append(outer[-1]["Plans"][0])
            assert [step["Node Type"] for step in outer if step["Node Type"] == "Sort"] == []
            scan = outer[-1]
            assert scan["Index Name"] == "ix_products_first_seen_at_id"
            assert scan["Scan Direction"] == "Backward"
            assert scan["Actual Rows"] == 49  # one page plus the probe row, never the table


# The Overview's numbers, recomputed in plain SQL straight from the tables (UX-4 verify).
SPOT_CHECK = text(
    """
    WITH latest AS (
        SELECT DISTINCT ON (s.listing_id) s.*, l.store_id, l.supplier_id
        FROM listing_snapshots s JOIN listings l ON l.id = s.listing_id
        WHERE l.product_id = :product AND l.delisted_at IS NULL
        ORDER BY s.listing_id, s.captured_at DESC, s.id DESC
    ), retail AS (
        SELECT * FROM latest
        WHERE store_id IS NOT NULL AND currency = 'USD' AND price_min_minor IS NOT NULL
    ), offers AS (
        SELECT * FROM latest
        WHERE supplier_id IS NOT NULL AND currency = 'USD' AND price_min_minor IS NOT NULL
          AND available IS NOT FALSE AND coalesce(stock, 1) > 0
    )
    SELECT
        (SELECT min(price_min_minor) FROM retail) AS price_min,
        (SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY price_min_minor) FROM retail)
            AS price_median,
        (SELECT max(coalesce(price_max_minor, price_min_minor)) FROM retail) AS price_max,
        (SELECT min(price_min_minor) FROM offers) AS best_cost,
        (SELECT count(DISTINCT store_id) FROM latest) AS stores,
        (SELECT count(*) FROM latest WHERE supplier_id IS NOT NULL) AS offers,
        (SELECT CASE WHEN EXISTS (
                    SELECT FROM listing_snapshots s JOIN listings l ON l.id = s.listing_id
                    WHERE l.product_id = p.id)
                THEN (now() AT TIME ZONE 'UTC')::date - (p.first_seen_at AT TIME ZONE 'UTC')::date
                END
         FROM products p WHERE p.id = :product) AS age_days,
        (SELECT round(velocity_7d) FROM product_daily_features
         WHERE product_id = :product AND family IN ('shp_inv', 'shp_bump', 'cj_stock')
           AND velocity_7d IS NOT NULL AND growth_7d IS NOT NULL
         ORDER BY feature_date DESC,
                  array_position(ARRAY['shp_inv', 'shp_bump', 'cj_stock'], family::text),
                  feature_version DESC
         LIMIT 1) AS velocity
    """
)


def feature(product: Product, family: str, days_ago: int, v7: float, growth: float | None) -> Any:
    return ProductDailyFeature(
        product_id=product.id,
        feature_date=(NOW - timedelta(days=days_ago)).date(),
        family=family,
        feature_version="1",
        velocity_7d=v7,
        growth_7d=growth,
        coverage=1,
        has_gap=False,
    )


@pytest.fixture
def overview_products(db_engine: Engine) -> dict[str, Any]:
    """Five products that cover every Overview branch, with the payload ids the test traces."""
    with Session(db_engine) as session:
        cj = Supplier(platform="cj", external_id="cj", name="CJ Dropshipping")  # one row, as CJ
        stores = [Store(domain=f"o{i}.example.test", platform="shopify") for i in range(6)]
        names = ("full", "unmatched", "even", "out_of_stock", "single")
        products = {
            name: Product(name=name, first_seen_at=NOW - timedelta(days=9)) for name in names
        }
        session.add_all([cj, *stores, *products.values()])
        session.flush()

        full = products["full"]
        a = listing(session, full, 1, store_id=stores[0].id)
        first = snapshot(session, a, 200, price_min_minor=1900, price_max_minor=4500)  # superseded
        snapshot(session, a, 5, price_min_minor=2400, price_max_minor=3900)
        a2 = listing(session, full, 1, store_id=stores[0].id)  # a second listing, same store
        median = snapshot(session, a2, 7, price_min_minor=2600)
        snapshot(session, listing(session, full, 1, store_id=stores[1].id), 4, price_min_minor=2900)
        top = snapshot(
            session,
            listing(session, full, 1, store_id=stores[2].id),
            6,
            price_min_minor=3100,
            price_max_minor=5200,
        )
        cad = listing(session, full, 1, store_id=stores[3].id)
        snapshot(session, cad, 3, price_min_minor=100, currency="CAD")  # a store, no USD price
        gone = listing(session, full, 1, store_id=stores[4].id, delisted_at=NOW)
        snapshot(session, gone, 1, price_min_minor=50)
        offer = {"supplier_id": cj.id}
        snapshot(session, listing(session, full, 2, **offer), 9, price_min_minor=800)
        snapshot(
            session, listing(session, full, 2, **offer), 8, price_min_minor=650, available=False
        )
        snapshot(session, listing(session, full, 2, **offer), 8, price_min_minor=700, stock=0)
        cheapest = snapshot(
            session, listing(session, full, 2, **offer), 8, price_min_minor=720, stock=5
        )
        session.add_all(
            [
                feature(full, "shp_bump", 1, 12.4, 0.3),
                feature(full, "shp_inv", 1, 20.6, 0.5),  # same day, better grade
                feature(full, "shp_inv", 3, 99, 0.9),  # an older day
            ]
        )

        even = products["even"]
        for store, price in zip(stores[:2], (3000, 1000), strict=True):
            snapshot(
                session, listing(session, even, 1, store_id=store.id), 2, price_min_minor=price
            )
        session.add(feature(even, "shp_inv", 1, 7, None))  # no growth yet: doesn't qualify

        out = products["out_of_stock"]
        snapshot(
            session, listing(session, out, 2, **offer), 2, price_min_minor=500, available=False
        )
        snapshot(session, listing(session, out, 2, **offer), 2, price_min_minor=600, stock=0)

        single = products["single"]
        snapshot(
            session, listing(session, single, 1, store_id=stores[5].id), 2, price_min_minor=1500
        )
        snapshot(
            session, listing(session, single, 2, **offer), 2, price_min_minor=900, currency="CAD"
        )
        cheap_gone = listing(session, single, 2, delisted_at=NOW, **offer)
        snapshot(session, cheap_gone, 2, price_min_minor=10)
        session.add(feature(single, "cj_stock", 2, 4.2, -0.1))
        session.commit()
        return {
            "ids": {name: str(product.id) for name, product in products.items()},
            "first": first.raw_payload_id,
            "median": median.raw_payload_id,
            "top": top.raw_payload_id,
            "cheapest": cheapest.raw_payload_id,
        }


@pytest.mark.db
def test_overview_stats_match_sql_spot_checks(
    api: TestClient, db_engine: Engine, overview_products: dict[str, Any]
) -> None:
    for name, product_id in overview_products["ids"].items():
        body = api.get(f"/v1/products/{product_id}/overview").json()
        counts = {item["vendor"]: item["count"]["value"] for item in body["appearances"]}
        with Session(db_engine) as session:
            expected = session.execute(SPOT_CHECK, {"product": product_id}).one()._asdict()
        assert {
            "price_min": body["price_min_minor"]["value"],
            "price_median": body["price_median_minor"]["value"],
            "price_max": body["price_max_minor"]["value"],
            "best_cost": body["best_supplier_cost_minor"]["value"],
            "stores": counts.get("store", 0),  # the API omits a source with no listing; never 0
            "offers": counts.get("supplier", 0),
            "age_days": body["age_days"]["value"],
            "velocity": body["velocity"]["value"],
        } == expected, name
        assert body["landed_margin_minor"] == {"value": None, "reason": NO_MARGIN}
        assert body["ad_count"]["value"] is None


@pytest.mark.db
def test_overview_traces_each_stat(api: TestClient, overview_products: dict[str, Any]) -> None:
    ids = overview_products["ids"]
    body = api.get(f"/v1/products/{ids['full']}/overview").json()
    assert body["currency"] == "USD"
    # 2,400 / 2,600 / 2,900 / 3,100 from four USD listings; the lower median is 2,600.
    assert body["price_median_minor"]["value"] == 2600
    assert body["price_median_minor"]["raw_payload_id"] == overview_products["median"]
    assert body["price_max_minor"]["raw_payload_id"] == overview_products["top"]
    cost = body["best_supplier_cost_minor"]
    assert (cost["value"], cost["platform"], cost["source"]) == (720, "cj", "cj")
    assert cost["raw_payload_id"] == overview_products["cheapest"]
    age = body["age_days"]
    assert (age["value"], age["source"], age["stale"]) == (9, "shopify_stores", False)
    assert age["raw_payload_id"] == overview_products["first"]  # the first observation
    assert body["velocity"] | {"as_of": None, "stale": None} == {
        "value": 21,
        "source": "shopify_stores",
        "source_name": "Shopify stores",
        "as_of": None,
        "raw_payload_id": None,
        "method": "Shopify inventory drops",
        "stale": None,
        "family": "shp_inv",
        "grade": "A",
        "growth": 0.5,
        "gap": False,
    }
    assert [(item["vendor"], item["count"]["source"]) for item in body["appearances"]] == [
        ("supplier", "cj"),
        ("store", "shopify_stores"),
    ]
    assert [item["count"]["value"] for item in body["appearances"]] == [4, 4]

    empty = api.get(f"/v1/products/{ids['unmatched']}/overview").json()
    assert empty["appearances"] == []
    for key in ("price_min_minor", "price_median_minor", "best_supplier_cost_minor", "age_days"):
        assert empty[key]["value"] is None and empty[key]["reason"], key
    assert empty["velocity"] == {"value": None, "reason": NO_SIGNAL}
    single = api.get(f"/v1/products/{ids['single']}/overview").json()
    assert single["velocity"]["grade"] == "unproven"
    assert single["best_supplier_cost_minor"]["value"] is None  # CAD only; the cheap one is gone


@pytest.mark.db
def test_overview_of_an_unknown_or_merged_product(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        survivor = Product(name="Survivor")
        session.add(survivor)
        session.flush()
        merged = Product(name="Merged", merged_into_id=survivor.id)
        session.add(merged)
        session.commit()
        merged_id = merged.id
    assert api.get(f"/v1/products/{uuid4()}/overview").status_code == 404
    response = api.get(f"/v1/products/{merged_id}/overview")
    assert (response.status_code, response.json()["code"]) == (409, "merged")
