from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.main import create_app
from pulso_core.models import (
    Category,
    CollectorRun,
    Image,
    Listing,
    ListingSnapshot,
    Product,
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
