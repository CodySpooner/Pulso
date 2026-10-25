"""GET /v1/popular-products (P2-29 b, DEC-267, DEC-272) on synthetic imports only: the repo is
public and Google's rows are internal use only, so no real export row appears here."""

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
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingVariant,
    PopularProduct,
    Product,
    RawPayload,
)

MERCHANT = 7  # seeded source id (migration 0009)
TODAY = datetime.now(UTC).date()
LATEST = TODAY - timedelta(days=TODAY.weekday())  # this week's Monday: never stale
PREVIOUS = LATEST - timedelta(days=7)


def gtin(body: str) -> str:
    """body plus its GS1 mod-10 check digit."""
    weighted = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str(-weighted % 10)


MERGED_GTIN = gtin("590123412345")


def test_popular_products_require_a_session(client: TestClient) -> None:
    assert client.get("/v1/popular-products").status_code == 401


@pytest.mark.parametrize("query", ["limit=0", "limit=501", "week=soon", "cursor=x"])
def test_popular_products_validate_the_query(client: TestClient, query: str) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    assert client.get(f"/v1/popular-products?{query}").status_code == 422


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


def get(api: TestClient, query: str = "") -> Any:
    response = api.get(f"/v1/popular-products{query}")
    assert response.status_code == 200, response.text
    return response.json()


def report(
    session: Session,
    week: date,
    category: str | None,
    rows: list[dict[str, Any]],
    captured_at: datetime | None = None,
) -> None:
    """One imported download: a capture and its ranked rows."""
    captured_at = captured_at or datetime.now(UTC)
    run = CollectorRun(source_id=MERCHANT, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=MERCHANT,
        run_id=run.id,
        captured_at=captured_at,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    for row in rows:
        session.add(
            PopularProduct(
                source_id=MERCHANT,
                country="US",
                category=category,
                observed_for=week,
                captured_at=captured_at,
                raw_payload_id=payload.id,
                parser_version="merchant-csv-v1",
                **row,
            )
        )
    session.flush()


def merged_product(session: Session) -> UUID:
    """A live product, and a product merged into it that carries MERGED_GTIN."""
    live = Product(name="Live")
    session.add(live)
    session.flush()
    merged = Product(name="Merged", merged_into_id=live.id)
    session.add(merged)
    session.flush()
    listing = Listing(source_id=1, external_id=uuid4().hex, url="https://example.test", title="M")
    listing.product_id = merged.id
    session.add(listing)
    session.flush()
    session.add(ListingVariant(listing_id=listing.id, external_id="v", barcode=MERGED_GTIN))
    session.flush()
    return live.id


def seed(db_engine: Engine) -> UUID:
    with Session(db_engine) as session:
        live = merged_product(session)
        report(
            session,
            PREVIOUS,
            "Apparel",
            [
                {"rank": 1, "title": "Example tee", "brand": None},
                {"rank": 5, "title": "Example linen shirt", "brand": "Acme"},
                {"rank": 6, "title": "Example hoodie", "brand": "Other brand"},  # not this brand
            ],
        )
        big = [
            {"rank": 4 + i, "title": f"Example big {i}", "brand": "BigCo" if i % 2 else "bigco"}
            for i in range(1, 11)
        ]  # 10 rows, one brand in two spellings: a major brand
        nine = [{"rank": 14 + i, "title": f"Example {i}", "brand": "Nine"} for i in range(1, 10)]
        report(
            session,
            LATEST,
            "Apparel",
            [
                {"rank": 1, "title": "Example linen shirt", "brand": "Acme", "currency": "USD",
                 "price_min_minor": 1999, "price_max_minor": 2499, "availability": "In stock"},
                {"rank": 2, "title": "Example tee", "brand": None, "gtins": MERGED_GTIN},
                {"rank": 3, "title": "Example hoodie", "brand": "Indie"},
                {"rank": 4, "title": "Example ranked by Google", "previous_rank": 9},
                *big,
                *nine,
            ],
        )  # fmt: skip
        report(session, LATEST, "Home", [{"rank": 1, "title": "Example lamp", "brand": "Acme"}])
        session.commit()
    return live


@pytest.mark.db
def test_nothing_imported_reads_empty(api: TestClient) -> None:
    page = get(api)
    assert (page["weeks"], page["categories"], page["rows"], page["as_of"]) == ([], [], [], None)
    assert page["source"] == "merchant_bestsellers" and page["total"] == 0


@pytest.mark.db
def test_newest_week_with_big_brands_hidden_and_weekly_change(
    api: TestClient, db_engine: Engine
) -> None:
    live = seed(db_engine)
    page = get(api)
    assert page["weeks"] == [str(LATEST), str(PREVIOUS)]
    assert (page["category"], page["categories"]) == ("Apparel", ["Apparel", "Home"])
    assert (page["as_of"], page["previous_week"], page["stale"]) == (
        str(LATEST),
        str(PREVIOUS),
        False,
    )
    assert (page["total"], page["hidden"], page["major_brand_rows"]) == (23, 10, 10)
    rows = {row["rank"]: row for row in page["rows"]}
    assert list(rows) == [1, 2, 3, 4, *range(15, 24)]  # BigCo's 10 rows hidden; Nine's 9 stay
    change = {rank: (r["change"]["basis"], r["change"]["value"]) for rank, r in rows.items()}
    assert change == {
        1: ("previous_week", 4),  # 5 → 1, matched on title and brand
        2: ("previous_week", -1),  # 1 → 2, both without a brand
        3: ("new", None),  # the same title under another brand last week: new, never 0
        4: ("previous_rank", 5),  # Google's previous rank wins
        **dict.fromkeys(range(15, 24), ("new", None)),
    }
    assert rows[1]["change"]["as_of"] == str(PREVIOUS)
    assert (rows[1]["price_min_minor"], rows[1]["price_max_minor"], rows[1]["currency"]) == (
        1999,
        2499,
        "USD",
    )
    assert rows[2]["product_id"] == str(live)  # the merged product's GTIN reaches the live one
    assert rows[2]["gtins"] == [MERGED_GTIN]
    assert rows[3]["product_id"] is None  # unlinked, and still listed
    assert all(row["as_of"] == str(LATEST) and not row["major_brand"] for row in rows.values())

    shown = get(api, "?include_major_brands=true")
    assert (len(shown["rows"]), shown["hidden"]) == (23, 0)
    assert [r["rank"] for r in shown["rows"] if r["major_brand"]] == list(range(5, 15))


@pytest.mark.db
def test_pages_by_rank_cursor_without_gaps(api: TestClient, db_engine: Engine) -> None:
    seed(db_engine)
    ranks, cursor = [], None
    for _ in range(10):
        page = get(
            api, "?include_major_brands=true&limit=4" + (f"&cursor={cursor}" if cursor else "")
        )
        ranks += [row["rank"] for row in page["rows"]]
        if (cursor := page["next_cursor"]) is None:
            break
    assert ranks == list(range(1, 24))
    assert get(api, "?limit=2&cursor=2")["rows"][0]["rank"] == 3  # hidden rows stay hidden


@pytest.mark.db
def test_category_week_and_staleness(api: TestClient, db_engine: Engine) -> None:
    seed(db_engine)
    home = get(api, "?category=Home")
    assert home["previous_week"] is None
    assert home["rows"][0]["change"] == {
        "value": None,
        "basis": "no_previous_week",
        "previous_rank": None,
        "as_of": None,
    }
    before = get(api, f"?week={PREVIOUS}")
    assert (before["as_of"], before["categories"], before["total"]) == (
        str(PREVIOUS),
        ["Apparel"],
        3,
    )
    assert get(api, f"?week={PREVIOUS}&category=Home")["rows"] == []  # not imported that week
    old = LATEST - timedelta(days=21)
    with Session(db_engine) as session:
        report(session, old, "Apparel", [{"rank": 1, "title": "Example old", "brand": None}])
        session.commit()
    assert get(api, f"?week={old}")["stale"] is True


@pytest.mark.db
def test_a_downloaded_again_report_shows_its_newest_capture_once(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        earlier = datetime.now(UTC) - timedelta(hours=2)
        report(session, LATEST, "Apparel", [{"rank": 1, "title": "Example a"}], earlier)
        report(session, LATEST, "Apparel", [{"rank": 1, "title": "Example b"}])
        session.commit()
    page = get(api)
    assert [row["title"] for row in page["rows"]] == ["Example b"] and page["total"] == 1
