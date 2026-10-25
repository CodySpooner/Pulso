"""GET /v1/amazon/ranks (AMZ-1b, DEC-286) on synthetic imports only: every ASIN and title here is
invented, and nothing is requested from Amazon (DEC-279)."""

import zlib
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import AmazonRank, CollectorRun, Listing, ListingVariant, Product, RawPayload

AMAZON = 8  # seeded source id (migration 0012)
TODAY = datetime.now(UTC).date()
EARLIER = TODAY - timedelta(days=3)
GTIN = "036000291452"


def test_amazon_ranks_require_a_session(client: TestClient) -> None:
    assert client.get("/v1/amazon/ranks").status_code == 401


@pytest.mark.parametrize(
    "query",
    ["limit=0", "limit=501", "rank_kind=top", "observed_for=soon", "cursor=x", "cursor=[1]"],
)
def test_amazon_ranks_validate_the_query(client: TestClient, query: str) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    assert client.get(f"/v1/amazon/ranks?{query}").status_code == 422


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


def get(api: TestClient, query: str = "", **params: Any) -> Any:
    response = api.get(f"/v1/amazon/ranks{query}", params=params or None)
    assert response.status_code == 200, response.text
    return response.json()


def ranks(page: Any) -> list[tuple[str, str, int, str]]:
    return [(r["category"], r["rank_kind"], r["rank"], r["title"]) for r in page["rows"]]


def imported(
    session: Session,
    day: date,
    rows: list[tuple[str, str, int, str]],
    captured_at: datetime | None = None,
) -> None:
    """One imported file: a capture and its (category, rank kind, rank, title) rows."""
    captured_at = captured_at or datetime.now(UTC)
    run = CollectorRun(source_id=AMAZON, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=AMAZON,
        run_id=run.id,
        captured_at=captured_at,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    for category, kind, rank, title in rows:
        session.add(
            AmazonRank(
                asin=f"B0{zlib.crc32(title.encode()) % 10**8:08d}",  # one ASIN per title
                category=category,
                rank_kind=kind,
                rank=rank,
                title=title,
                price_minor=2499 if rank == 1 else None,
                currency="USD",
                rating=4.6 if rank == 1 else None,
                review_count=1532 if rank == 1 else None,
                gtins=GTIN if title == "Lamp" else None,
                observed_for=day,
                captured_at=captured_at,
                raw_payload_id=payload.id,
                parser_version="amazon-csv-v1",
            )
        )
    session.flush()


def product_with_gtin(session: Session) -> UUID:
    product = Product(name="Desk lamp")
    session.add(product)
    session.flush()
    listing = Listing(source_id=1, external_id=uuid4().hex, url="https://example.test", title="L")
    listing.product_id = product.id
    session.add(listing)
    session.flush()
    session.add(ListingVariant(listing_id=listing.id, external_id="v", barcode="0" + GTIN))
    session.flush()
    return product.id


def seed(db_engine: Engine) -> UUID:
    """Two days of Home (both lists) and one of Toys: Home's earlier day is superseded."""
    with Session(db_engine) as session:
        product = product_with_gtin(session)
        imported(session, EARLIER, [("Home", "bsr", 1, "Old lamp"), ("Home", "bsr", 2, "Old mug")])
        imported(session, EARLIER, [("Toys", "bsr", 1, "Kite"), ("Toys", "bsr", 2, "Yo-yo")])
        imported(
            session,
            TODAY,
            [
                ("Home", "bsr", 1, "Lamp"),
                ("Home", "bsr", 2, "Mug"),
                ("Home", "bsr", 3, "Rug"),
                ("Home", "movers", 1, "Fan"),
                ("Home", "movers", 2, "Lamp"),
            ],
        )
        session.commit()
    return product


@pytest.mark.db
def test_nothing_imported_reads_empty(api: TestClient) -> None:
    page = get(api)
    assert (page["source"], page["source_name"]) == ("amazon", "Amazon")
    assert (page["lists"], page["rows"], page["total"], page["as_of"]) == ([], [], 0, None)
    assert (page["stale"], page["next_cursor"]) == (False, None)


@pytest.mark.db
def test_no_source_row_reads_as_no_source_yet(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        session.execute(text("DELETE FROM sources WHERE key = 'amazon'"))
        session.commit()
    page = get(api)
    assert (page["source"], page["source_name"], page["rows"]) == (None, None, [])


@pytest.mark.db
def test_each_list_at_its_newest_day_ranked_within_its_own_category(
    api: TestClient, db_engine: Engine
) -> None:
    product = seed(db_engine)
    page = get(api)
    # Both rank 1s show, each under its own category and list; Home's earlier day doesn't.
    assert ranks(page) == [
        ("Home", "bsr", 1, "Lamp"),
        ("Home", "bsr", 2, "Mug"),
        ("Home", "bsr", 3, "Rug"),
        ("Home", "movers", 1, "Fan"),
        ("Home", "movers", 2, "Lamp"),
        ("Toys", "bsr", 1, "Kite"),
        ("Toys", "bsr", 2, "Yo-yo"),
    ]
    assert [r["as_of"] for r in page["rows"]] == [str(TODAY)] * 5 + [str(EARLIER)] * 2
    lists = [(x["category"], x["rank_kind"], x["as_of"], x["rows"]) for x in page["lists"]]
    assert lists == [
        ("Home", "bsr", str(TODAY), 3),
        ("Home", "movers", str(TODAY), 2),
        ("Toys", "bsr", str(EARLIER), 2),
    ]
    assert (page["total"], page["as_of"], page["stale"]) == (7, str(TODAY), False)
    lamp, mug = page["rows"][0], page["rows"][1]
    assert (lamp["price_minor"], lamp["currency"], lamp["rating"], lamp["review_count"]) == (
        2499,
        "USD",
        4.6,
        1532,
    )
    assert lamp["product_id"] == str(product)  # a UPC-12 reaching a 13-digit barcode
    assert page["rows"][4]["product_id"] == str(product)  # the same ASIN in the other list
    assert (mug["product_id"], mug["price_minor"], mug["rating"]) == (None, None, None)
    assert lamp["raw_payload_id"] and lamp["captured_at"] and len(lamp["asin"]) == 10


@pytest.mark.db
def test_pages_by_list_then_rank_without_gaps(api: TestClient, db_engine: Engine) -> None:
    seed(db_engine)
    every = ranks(get(api))
    seen, cursor, pages = [], None, 0
    while True:
        page = get(api, limit=2, **({"cursor": cursor} if cursor else {}))
        seen += ranks(page)
        pages += 1
        if (cursor := page["next_cursor"]) is None:
            break
    assert (seen, pages) == (every, 4)
    assert get(api, "?limit=7")["next_cursor"] is None


@pytest.mark.db
def test_filters_narrow_the_lists(api: TestClient, db_engine: Engine) -> None:
    seed(db_engine)
    toys = get(api, "?category=Toys")
    assert ranks(toys) == [("Toys", "bsr", 1, "Kite"), ("Toys", "bsr", 2, "Yo-yo")]
    assert (toys["as_of"], toys["total"], len(toys["lists"])) == (str(EARLIER), 2, 3)
    movers = get(api, "?rank_kind=movers")
    assert ranks(movers) == [("Home", "movers", 1, "Fan"), ("Home", "movers", 2, "Lamp")]
    before = get(api, f"?observed_for={EARLIER}&category=Home")
    assert ranks(before) == [("Home", "bsr", 1, "Old lamp"), ("Home", "bsr", 2, "Old mug")]
    assert get(api, "?category=Garden")["rows"] == []


@pytest.mark.db
def test_a_reimported_day_shows_its_newest_capture_once(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        earlier = datetime.now(UTC) - timedelta(hours=2)
        imported(session, TODAY, [("Home", "bsr", 1, "Wrong"), ("Home", "bsr", 2, "Gone")], earlier)
        imported(session, TODAY, [("Home", "bsr", 1, "Right")])
        session.commit()
    page = get(api)
    assert (ranks(page), page["total"]) == ([("Home", "bsr", 1, "Right")], 1)


@pytest.mark.db
@pytest.mark.parametrize(("days", "stale"), [(14, False), (15, True)])
def test_stale_when_the_newest_day_is_over_14_days_old(
    api: TestClient, db_engine: Engine, days: int, stale: bool
) -> None:
    day = TODAY - timedelta(days=days)
    with Session(db_engine) as session:
        imported(session, day, [("Home", "bsr", 1, "Lamp")])
        session.commit()
    assert get(api)["stale"] is stale
    assert get(api, f"?observed_for={day}")["stale"] is False  # an earlier day picked on purpose
