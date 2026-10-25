from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import (
    CollectionGap,
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    RawPayload,
    Store,
)

# The Trends series (UX-5, DEC-245): points only on days the source collected, gaps from
# source_daily_coverage, and day d built only from captures before d + 1 00:00Z.
TODAY = datetime.now(UTC).date()
SHOPIFY = 1


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def at(day: date, hour: int = 0) -> datetime:
    return datetime.combine(day, time(hour), UTC)


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


def payload(session: Session, status: str = "success", started: datetime | None = None) -> int:
    run = CollectorRun(source_id=SHOPIFY, trigger="manual", status=status, started_at=started)
    session.add(run)
    session.flush()
    raw = RawPayload(source_id=SHOPIFY, run_id=run.id, request={}, bytes=1, sha256=uuid4().hex * 2)
    session.add(raw)
    session.flush()
    return raw.id


def coverage(session: Session, **days: str) -> None:
    """One source_daily_coverage status per day ago: d5="success", d3="gap", d0="failed"."""
    for key, status in days.items():
        day = ago(int(key[1:]))
        if status == "success":
            raw = payload(session, started=at(day, 6))
            run_id = session.get_one(RawPayload, raw).run_id
            session.add(
                CollectorRunTarget(
                    run_id=run_id,
                    scope="shopify_catalog",
                    target_id="s.example.test",
                    status="success",
                    raw_payload_id=raw,
                    captured_at=at(day, 6),
                )
            )
        elif status == "failed":
            payload(session, status="failed", started=at(day, 6))
        else:  # the collector host was off 01:00-08:30
            slot = at(day, 1)
            session.add(
                CollectionGap(
                    source_id=SHOPIFY,
                    slot_key=day.isoformat(),
                    slot_start=slot,
                    slot_end=slot + timedelta(hours=7.5),
                    reason="host_offline",
                )
            )
    session.flush()


def store_listing(session: Session, product: Product, **values: Any) -> Listing:
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    session.add(store)
    session.flush()
    row = Listing(
        source_id=SHOPIFY,
        external_id=uuid4().hex,
        url="https://example.test/p",
        title="Sunset lamp",
        product_id=product.id,
        store_id=store.id,
        **values,
    )
    session.add(row)
    session.flush()
    return row


def snapshot(session: Session, listing: Listing, captured_at: datetime, **values: Any) -> None:
    session.add(
        ListingSnapshot(
            listing_id=listing.id,
            captured_at=captured_at,
            observed_for=captured_at.date(),
            raw_payload_id=payload(session),
            values_hash=uuid4().hex,
            currency=values.pop("currency", "USD"),
            **values,
        )
    )
    session.flush()


def series(api: TestClient, product_id: object, **query: str) -> dict[str, dict[str, Any]]:
    response = api.get(f"/v1/products/{product_id}/series", params=query)
    assert response.status_code == 200, response.json()
    return {s["metric"]: s for s in response.json()["series"]}


def points(item: dict[str, Any]) -> list[tuple[date, int, int | None]]:
    return [(date.fromisoformat(p["day"]), p["value"], p["high"]) for p in item["points"]]


@pytest.mark.db
def test_points_only_on_collected_days_and_gaps_from_coverage(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        product = Product(name="Sunset lamp")
        session.add(product)
        session.flush()
        a = store_listing(session, product)
        snapshot(session, a, at(ago(5), 9), price_min_minor=2400, price_max_minor=3900)
        # Captured at day -4's cutoff exactly, so it first counts on day -3 (a gap): day -2.
        snapshot(session, a, at(ago(3)), price_min_minor=2200, price_max_minor=3900)
        b = store_listing(session, product, delisted_at=at(ago(1), 10))
        snapshot(session, b, at(ago(5), 10), price_min_minor=2600)
        coverage(session, d5="success", d4="success", d3="gap", d2="success", d1="success")
        coverage(session, d0="failed")  # day -6 has no record at all
        session.commit()
        product_id = product.id

    body = api.get(f"/v1/products/{product_id}/series", params={"range": "7d"}).json()
    assert (body["start"], body["end"]) == (ago(6).isoformat(), TODAY.isoformat())
    by_metric = {s["metric"]: s for s in body["series"]}
    price, stores = by_metric["price"], by_metric["store_count"]
    # Day -4 is collected but unchanged, so it carries day -5's snapshots; nothing is filled in on
    # day -6 (no record), -3 (gap) or 0 (failed). B is delisted during day -1.
    assert points(stores) == [
        (ago(5), 2, None),
        (ago(4), 2, None),
        (ago(2), 2, None),
        (ago(1), 1, None),
    ]
    assert points(price) == [
        (ago(5), 2400, 3900),
        (ago(4), 2400, 3900),
        (ago(2), 2200, 3900),
        (ago(1), 2200, 3900),
    ]
    as_of = [datetime.fromisoformat(p["as_of"]) for p in price["points"]]
    assert as_of == [at(ago(5), 10), at(ago(5), 10), at(ago(3)), at(ago(3))]
    for item in (price, stores):
        assert all(
            datetime.fromisoformat(p["as_of"])
            < at(date.fromisoformat(p["day"]) + timedelta(days=1))
            for p in item["points"]
        )
        assert item["gaps"] == [
            {"day": ago(3).isoformat(), "status": "gap"},
            {"day": TODAY.isoformat(), "status": "failed"},
        ]
        assert (item["source"], item["source_name"], item["unit"] != "") == (
            "shopify_stores",
            "Shopify stores",
            True,
        )
    assert datetime.fromisoformat(price["as_of"]) == at(ago(3))  # the newest priced capture


@pytest.mark.db
def test_velocity_reads_the_newest_feature_version_and_no_gaps(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        product = Product(name="Sunset lamp")
        session.add(product)
        session.flush()
        snapshot(session, store_listing(session, product), at(ago(2), 9), price_min_minor=2400)
        coverage(session, d2="success", d1="success", d0="success")
        for day, version, v7 in ((3, "1", 4.4), (2, "1", None), (1, "1", 7.6), (1, "2", 9.0)):
            session.add(
                ProductDailyFeature(
                    product_id=product.id,
                    feature_date=ago(day),
                    family="shp_bump",
                    feature_version=version,
                    velocity_7d=v7,
                    coverage=1,
                    has_gap=v7 is None,
                )
            )
        session.commit()
        product_id = product.id

    got = series(api, product_id, range="7d")
    assert points(got["store_count"]) == [(ago(2), 1, None), (ago(1), 1, None), (TODAY, 1, None)]
    assert got["store_count"]["gaps"] == got["price"]["gaps"] == []
    bumps = got["velocity_bumps"]
    assert points(bumps) == [(ago(3), 4, None), (ago(1), 9, None)]  # day -2 is gapped: no point
    assert bumps["gaps"] == []
    assert bumps["method"] == "Shopify updated_at bumps, a lower bound (grade B)"
    assert datetime.fromisoformat(bumps["as_of"]) == at(TODAY)  # day -1's data ends at 00:00Z
    assert got["velocity_js"] == {
        "metric": "velocity_js",
        "value": None,
        "reason": "No velocity computed from Shopify inventory drops yet.",
    }


@pytest.mark.db
def test_series_nothing_backs_say_why(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        bare, cad = Product(name="Unmatched"), Product(name="Canadian only")
        session.add_all([bare, cad])
        session.flush()
        snapshot(
            session, store_listing(session, cad), at(ago(1), 9), price_min_minor=100, currency="CAD"
        )
        coverage(session, d1="success")
        session.commit()
        ids = (bare.id, cad.id)

    got = series(api, ids[0])
    assert [s.get("reason") for s in got.values()] == [
        "No store listing matched yet.",
        "No store listing matched yet.",
        (
            "No search interest is collected for this product's keywords yet. Tracked keywords are "
            "fetched from Google Trends each Monday when tracking is on."
        ),
        "No velocity computed from Shopify inventory drops yet.",
        "No velocity computed from Shopify updated_at bumps yet.",
        "No ad source yet. Ad counts arrive in Phase 8 or by CSV import.",
    ]
    assert all(s["value"] is None and "points" not in s for s in got.values())  # never zeros
    got = series(api, ids[1], metrics="price,store_count")
    assert got["price"]["reason"] == "No USD retail price observed yet."
    assert points(got["store_count"]) == [(ago(1), 1, None)]


@pytest.mark.db
def test_ranges_metrics_merges_and_workspaces(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        survivor = Product(name="Survivor", first_seen_at=at(ago(2)))
        session.add(survivor)
        session.flush()
        merged = Product(name="Merged", merged_into_id=survivor.id)
        session.add(merged)
        snapshot(session, store_listing(session, survivor), at(ago(5), 9), price_min_minor=2400)
        coverage(session, d40="gap", d5="success")
        session.commit()
        ids = (merged.id, survivor.id)

    url = f"/v1/products/{ids[0]}/series?range=7d&metrics=price"
    response = api.get(url, follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == f"../{ids[1]}/series?range=7d&metrics=price"
    followed = api.get(url).json()
    assert followed["id"] == str(ids[1])
    assert [s["metric"] for s in followed["series"]] == ["price"]
    # `all` starts at the first point (before first seen); the gap before it drops out.
    everything = api.get(f"/v1/products/{ids[1]}/series", params={"range": "all"}).json()
    assert everything["start"] == ago(5).isoformat()
    assert {s["metric"]: s.get("gaps") for s in everything["series"]}["price"] == []
    month = api.get(f"/v1/products/{ids[1]}/series", params={"range": "30d"}).json()
    assert month["start"] == ago(29).isoformat()
    for query in ({"range": "14d"}, {"metrics": "price,orders"}, {"metrics": ""}):
        assert api.get(f"/v1/products/{ids[1]}/series", params=query).status_code == 422, query
    assert api.get(f"/v1/products/{uuid4()}/series").status_code == 404
    # Global market data: another workspace sees the same series.
    first = api.get(f"/v1/products/{ids[1]}/series").json()
    assert len(first["series"]) == 6
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    assert api.get(f"/v1/products/{ids[1]}/series").json() == first


def test_series_requires_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}/series").status_code == 401
