"""GET /v1/products/{id}/sellers (UX-7, DEC-247) on fixture rows only."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    FxRate,
    Listing,
    ListingSnapshot,
    Product,
    RawPayload,
    Source,
    Store,
    Workspace,
    WorkspaceTrackedStore,
)

NOW = datetime.now(UTC)


def ago(days: float) -> datetime:
    return NOW - timedelta(days=days)


def test_sellers_require_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}/sellers").status_code == 401


def payload(session: Session) -> RawPayload:
    run = CollectorRun(source_id=1, trigger="manual", status="success")
    session.add(run)
    session.flush()
    row = RawPayload(source_id=1, run_id=run.id, request={}, bytes=1, sha256=uuid4().hex * 2)
    session.add(row)
    session.flush()
    return row


def crawl(session: Session, domain: str, status: str, days_ago: float) -> None:
    raw = payload(session)
    session.add(
        CollectorRunTarget(
            run_id=raw.run_id,
            scope="shopify_catalog",
            target_id=domain,
            status=status,
            raw_payload_id=raw.id if status != "failed" else None,
            captured_at=ago(days_ago),
        )
    )


def seller(
    session: Session,
    product: Product,
    name: str,
    *,
    price: int | None = None,
    currency: str = "USD",
    store_status: str = "active",
    store_days: float = 60,
    seen_days: float = 40,
    snapshot_days: float = 1,
    crawl_status: str | None = "success",
    **listing: Any,
) -> Listing:
    store = Store(
        domain=f"{name}.example.test",
        platform="shopify",
        status=store_status,
        first_seen_at=ago(store_days),
    )
    session.add(store)
    session.flush()
    row = Listing(
        source_id=1,
        external_id=uuid4().hex,
        url=f"https://{store.domain}/products/lamp",
        title="Sunset lamp",
        product_id=product.id,
        store_id=store.id,
        first_seen_at=ago(seen_days),
        last_seen_at=ago(0.0001),
        **listing,
    )
    session.add(row)
    session.flush()
    if price is not None:
        session.add(
            ListingSnapshot(
                listing_id=row.id,
                captured_at=ago(snapshot_days),
                observed_for=ago(snapshot_days).date(),
                raw_payload_id=payload(session).id,
                values_hash=uuid4().hex,
                price_min_minor=price,
                currency=currency,
            )
        )
    if crawl_status is not None:
        crawl(session, store.domain, crawl_status, 0.0001)
    return row


@pytest.fixture
def sellers(client: TestClient, db_engine: Engine) -> Iterator[dict[str, Any]]:
    with Session(db_engine) as session:
        session.get_one(Source, 1).config = {"expected_interval": 21600}
        product = Product(name="Sunset lamp")
        workspaces = [Workspace(name="A"), Workspace(name="B")]
        session.add_all([product, *workspaces])
        session.flush()
        rows = {
            "listed": seller(session, product, "listed", price=2400, source_created_at=ago(30)),
            "gone": seller(session, product, "gone", price=1000, delisted_at=ago(3)),
            "partial": seller(session, product, "partial", price=2600, crawl_status="partial"),
            "blocked": seller(
                session,
                product,
                "blocked",
                price=2200,
                store_status="blocked",
                crawl_status="failed",
            ),
            "untrackable": seller(
                session, product, "untrackable", price=100, store_status="untrackable"
            ),
            "cad": seller(session, product, "cad", price=4000, currency="CAD", snapshot_days=2),
            "eur": seller(session, product, "eur", price=3000, currency="EUR"),
            "new": seller(
                session, product, "new", price=2000, seen_days=5, source_created_at=ago(5)
            ),
            # Pulso found this store 3 days ago: not on the stable panel, so not "new" (review M15).
            "fresh": seller(session, product, "fresh", price=2800, store_days=3, seen_days=2),
        }
        crawl(session, "gone.example.test", "success", 3)  # the complete crawl that delisted it
        crawl(session, "listed.example.test", "success", 10)
        crawl(session, "listed.example.test", "partial", 1)  # a partial day is still a gap
        # CAD per USD on the snapshot's date, then a later rate that must not apply.
        for days, rate in ((2, "1.25"), (0, "2")):
            raw = payload(session)
            session.add(
                FxRate(
                    date=ago(days).date(),
                    base="USD",
                    quote="CAD",
                    source="frankfurter_blended",
                    rate=Decimal(rate),
                    captured_at=ago(days),
                    observed_for=ago(days).date(),
                    raw_payload_id=raw.id,
                )
            )
        session.add_all(
            [
                WorkspaceTrackedStore(workspace_id=workspaces[0].id, store_id=rows["new"].store_id),
                WorkspaceTrackedStore(
                    workspace_id=workspaces[1].id, store_id=rows["listed"].store_id
                ),
            ]
        )
        session.commit()
        ids = {key: row.id for key, row in rows.items()}
        product_id, a, b = product.id, workspaces[0].id, workspaces[1].id

    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), a)
    yield {"api": client, "product": product_id, "ids": ids, "a": a, "b": b}


def get(fx: dict[str, Any], **params: Any) -> dict[str, Any]:
    response = fx["api"].get(f"/v1/products/{fx['product']}/sellers", params=params)
    assert response.status_code == 200, response.json()
    body: dict[str, Any] = response.json()
    return body


def by_name(fx: dict[str, Any], body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    names = {listing_id: name for name, listing_id in fx["ids"].items()}
    return {names[row["listing_id"]]: row for row in body["rows"]}


@pytest.mark.db
def test_only_a_complete_crawl_delists(sellers: dict[str, Any]) -> None:
    rows = by_name(sellers, get(sellers, include_delisted=True, limit=200))
    assert set(rows) == set(sellers["ids"])
    gone = rows["gone"]
    assert gone["listed"] == "delisted"
    assert datetime.fromisoformat(gone["delisted_at"]) == ago(3)
    assert (rows["listed"]["listed"], rows["listed"]["unknown_reason"]) == ("listed", None)
    # Omitted by a partial or blocked crawl: Unknown, never Delisted.
    assert (rows["partial"]["listed"], rows["partial"]["unknown_reason"]) == (
        "unknown",
        "last_crawl_incomplete",
    )
    assert rows["blocked"]["unknown_reason"] == "store_blocked"
    assert rows["untrackable"]["unknown_reason"] == "store_untrackable"
    assert all(row["delisted_at"] is None for name, row in rows.items() if name != "gone")
    assert list(rows)[-1] == "gone"  # active rows first
    # Active only by default.
    assert "gone" not in by_name(sellers, get(sellers))


@pytest.mark.db
def test_rows_carry_price_start_and_provenance(sellers: dict[str, Any]) -> None:
    rows = by_name(sellers, get(sellers, limit=200))
    listed = rows["listed"]
    assert (listed["price_usd_minor"], listed["currency"], listed["fx_missing"]) == (
        2400,
        "USD",
        False,
    )
    assert (listed["started_basis"], datetime.fromisoformat(listed["started_at"])) == (
        "store",
        ago(30),
    )
    assert (rows["fresh"]["started_basis"], rows["fresh"]["domain"]) == (
        "first_seen",
        "fresh.example.test",
    )
    assert (
        listed["raw_payload_id"] and listed["as_of"] and listed["source_name"] == "Shopify stores"
    )
    assert listed["running_ads"]["value"] is None and listed["running_ads"]["reason"]
    assert listed["stale"] is False
    # CAD at the snapshot date's rate (1.25), not today's (2); EUR has no rate, so no price.
    assert (rows["cad"]["price_usd_minor"], rows["cad"]["price_minor"]) == (3200, 4000)
    assert (rows["eur"]["price_usd_minor"], rows["eur"]["fx_missing"]) == (None, True)


@pytest.mark.db
def test_spread_counts_and_band(sellers: dict[str, Any]) -> None:
    body = get(sellers)
    spread = body["spread"]
    # Active, trackable, priced: 2000 2200 2400 2600 2800 3200. Delisted (1000), untrackable
    # (100) and EUR without a rate stay out and are counted.
    assert {k: spread[k] for k in ("min", "p25", "median", "mean", "p75", "max", "n")} == {
        "min": 2000,
        "p25": 2250,
        "median": 2500,
        "mean": 2533,
        "p75": 2750,
        "max": 3200,
        "n": 6,
    }
    assert (spread["missing"], spread["untrackable"]) == (1, 1)
    assert [p["price_usd_minor"] for p in spread["points"]] == [2000, 2200, 2400, 2600, 2800, 3200]
    assert body["counts"] | {"as_of": None} == {
        "active": 8,
        "delisted_30d": 1,
        "new_14d": 1,
        "as_of": None,
    }
    assert body["band"] == {"low": None, "high": None, "reason": "needs_landed_cost"}
    new = by_name(sellers, get(sellers, new_14d=True))
    assert list(new) == ["new"]


@pytest.mark.db
def test_series_marks_gaps_and_never_interpolates(sellers: dict[str, Any]) -> None:
    days = {d["date"]: d for d in get(sellers)["series_90d"]}
    assert len(days) == 90

    def on(n: int) -> tuple[int | None, bool]:
        day = days[(NOW.date() - timedelta(days=n)).isoformat()]
        return day["active"], day["gap"]

    assert on(0) == (8, False)
    assert on(1) == (None, True)  # only a partial crawl that day
    assert on(3) == (7, False)  # "gone" delisted that day; "new" (first seen day 5) counts
    assert on(5) == (None, True)
    assert on(10) == (7, False)  # before "new" and "fresh"; "gone" still live


@pytest.mark.db
def test_cursor_pages_every_row_once(sellers: dict[str, Any]) -> None:
    rows, cursor = [], None
    while True:
        body = get(
            sellers, include_delisted=True, limit=2, **({"cursor": cursor} if cursor else {})
        )
        rows += [row["listing_id"] for row in body["rows"]]
        if (cursor := body["next_cursor"]) is None:
            break
    whole = get(sellers, include_delisted=True, limit=200)
    assert rows == [row["listing_id"] for row in whole["rows"]]
    assert len(rows) == len(set(rows)) == len(sellers["ids"])
    bad = sellers["api"].get(f"/v1/products/{sellers['product']}/sellers", params={"cursor": "x"})
    assert (bad.status_code, bad.json()["code"]) == (422, "invalid_cursor")


@pytest.mark.db
def test_tracked_flag_is_per_workspace(sellers: dict[str, Any]) -> None:
    def tracked(workspace: UUID) -> set[str]:
        sellers["api"].app.dependency_overrides[current_principal] = lambda: Principal(
            uuid4(), workspace
        )
        return {name for name, row in by_name(sellers, get(sellers)).items() if row["tracked"]}

    assert tracked(sellers["a"]) == {"new"}
    assert tracked(sellers["b"]) == {"listed"}
    assert list(by_name(sellers, get(sellers, tracked=True))) == ["listed"]


@pytest.mark.db
def test_crawler_state_comes_from_the_source(sellers: dict[str, Any], db_engine: Engine) -> None:
    assert get(sellers)["crawler"] == {"status": "disabled", "since": None, "reason": None}
    with Session(db_engine) as session:
        source = session.get_one(Source, 1)
        source.status, source.disabled_at = "blocked", ago(2)
        source.disabled_reason = "consecutive_blocks:http_429"
        session.commit()
    crawler = get(sellers)["crawler"]
    assert (crawler["status"], crawler["reason"]) == (
        "auto_disabled",
        "consecutive_blocks:http_429",
    )
    assert datetime.fromisoformat(crawler["since"]) == ago(2)


@pytest.mark.db
def test_merged_and_unknown_products(sellers: dict[str, Any], db_engine: Engine) -> None:
    with Session(db_engine) as session:
        merged = Product(name="Merged", merged_into_id=sellers["product"])
        session.add(merged)
        session.commit()
        merged_id = merged.id
    api: TestClient = sellers["api"]
    url = f"/v1/products/{merged_id}/sellers?include_delisted=true"
    response = api.get(url, follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == f"../{sellers['product']}/sellers?include_delisted=true"
    followed = api.get(url)
    assert followed.status_code == 200
    assert len(followed.json()["rows"]) == len(sellers["ids"])
    assert api.get(f"/v1/products/{uuid4()}/sellers").status_code == 404
