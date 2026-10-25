"""Amazon best-seller CSV (p3-01, DEC-279). Every row here is synthetic, never real Amazon data."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pulso_core.models import AmazonRank, Listing, ListingVariant, Product, RawPayload
from pulso_core.settings import Settings
from pulso_sources.amazon import ImportAdapter
from pulso_sources.framework import UpsertStats
from pulso_sources.imports import ADAPTERS, ImportData, commit_import, parse_csv, template_csv
from pulso_sources.imports.csv import DuplicateEntityRows, RowError
from pulso_sources.merchant_bestsellers import link_products

KEY = "amazon"
FIXTURE = (Path(__file__).parent / "fixtures" / "amazon.csv").read_bytes()
HEADER = "asin,title,category,rank,rank_kind,price,currency,rating,review_count,gtins,observed_for"


def test_template_and_fixture_parse() -> None:
    assert template_csv(KEY) == f"{HEADER}\r\n".encode()
    parsed = parse_csv(KEY, FIXTURE)
    assert (parsed.errors, len(parsed.rows)) == ([], 3)
    assert parsed.rows[0] == {
        "asin": "B0EXAMPLE1",
        "title": "Example LED desk lamp",
        "category": "Home & Kitchen",
        "rank": 1,
        "rank_kind": "bsr",
        "price": Decimal("24.99"),
        "currency": "USD",
        "rating": Decimal("4.6"),
        "review_count": 1532,
        "gtins": "036000291452",
        "observed_for": date(2026, 10, 19),
    }
    rows = ImportAdapter(ImportData("csv", parsed, None)).parse(b"")
    # Blank rank_kind and currency take the template defaults; blank values stay unknown.
    assert (rows[1].rank_kind, rows[1].currency, rows[1].price, rows[1].rating) == (
        "bsr",
        "USD",
        None,
        None,
    )


def test_whitespace_only_cells_take_the_column_default() -> None:
    """XR-44: a blank-after-stripping rank_kind or currency defaults like an empty cell, so the
    preview doesn't answer 500 and the run's parse accepts what the preview passed."""
    body = f"{HEADER}\r\nB0EXAMPLE1,Lamp,Toys,1, ,, ,,,,2026-10-19\r\n".encode()
    parsed = parse_csv(KEY, body, as_of=date(2026, 10, 25))
    assert parsed.errors == []
    assert (parsed.rows[0]["rank_kind"], parsed.rows[0]["currency"]) == ("bsr", "USD")
    assert ImportAdapter(ImportData("csv", parsed, None)).parse(b"")[0].currency == "USD"


def test_malformed_rows_are_rejected_with_row_numbers() -> None:
    body = (
        f"{HEADER}\r\n"
        "B0EXAMPLE1,Fine,Toys,1,bsr,5,USD,4,10,,2026-10-19\r\n"
        "B0BAD,Short ASIN,Toys,2,bsr,5,USD,4,10,,2026-10-19\r\n"
        "B0EXAMPLE3,Rank zero,Toys,0,bsr,5,USD,4,10,,2026-10-19\r\n"
        "B0EXAMPLE4,Rating above five,Toys,4,bsr,5,USD,5.5,10,,2026-10-19\r\n"
        "B0EXAMPLE5,Unknown list,Toys,5,top,5,USD,4,10,,2026-10-19\r\n"
        "B0EXAMPLE6,,Toys,6,bsr,-1,USD,4,10,,2026-10-19\r\n"
    ).encode()
    parsed = parse_csv(KEY, body, as_of=date(2026, 10, 25))
    assert [row["asin"] for row in parsed.rows] == ["B0EXAMPLE1"]
    assert parsed.errors == [
        RowError(3, "asin", "Invalid asin value"),
        RowError(4, "rank", "Must be at least 1"),
        RowError(5, "rating", "Invalid rating value"),
        RowError(6, "rank_kind", "Use bsr or movers"),
        RowError(7, "title", "Required field is missing"),
        RowError(7, "price", "Invalid money value"),
    ]
    twice = f"{HEADER}\r\n" + "B0EXAMPLE1,Lamp,Toys,1,bsr,5,USD,4,10,,2026-10-19\r\n" * 2
    with pytest.raises(DuplicateEntityRows) as duplicate:
        parse_csv(KEY, twice.encode())
    assert [error.row for error in duplicate.value.errors] == [2, 3]


@pytest.fixture
def db(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.setitem(ADAPTERS, KEY, ImportAdapter)  # conftest swaps in FakeAdapter
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.mark.db
def test_reimporting_the_same_file_writes_no_new_rows(
    db: Session, settings: Settings, s3: MagicMock
) -> None:
    first = commit_import(db, KEY, FIXTURE, settings=settings)
    assert (first.status, first.rows_inserted) == ("success", 3), first.error_message
    again = commit_import(db, KEY, FIXTURE, settings=settings)
    assert again.status == "skipped" and again.params["original_run_id"] == first.id
    rows = db.scalars(select(AmazonRank).order_by(AmazonRank.id)).all()
    assert [(row.asin, row.rank_kind, row.rank) for row in rows] == [
        ("B0EXAMPLE1", "bsr", 1),
        ("B0EXAMPLE2", "bsr", 2),
        ("B0EXAMPLE1", "movers", 7),
    ]
    top = rows[0]
    assert (top.price_minor, top.currency, top.rating, top.review_count) == (
        2499,
        "USD",
        Decimal("4.60"),
        1532,
    )
    assert (rows[1].price_minor, rows[1].rating, rows[1].review_count) == (None, None, None)
    assert top.observed_for == date(2026, 10, 19)
    assert top.raw_payload_id == first.params["raw_payload_id"]
    assert top.captured_at.date() == datetime.now(UTC).date()
    # The capture parsed again by the same parser meets the unique key and adds nothing.
    payload = db.get_one(RawPayload, top.raw_payload_id)
    adapter = ImportAdapter(ImportData("csv", parse_csv(KEY, FIXTURE), None))
    stats = adapter.upsert(db, adapter.parse(b""), payload, parser_version=adapter.parser_version)
    assert stats == UpsertStats(inserted=0, unchanged=3)
    assert db.scalar(select(func.count()).select_from(AmazonRank)) == 3
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("UPDATE amazon_ranks SET rank = 3"))
    db.rollback()


@pytest.mark.db
def test_a_gtin_row_resolves_to_its_product(db: Session, settings: Settings, s3: MagicMock) -> None:
    assert commit_import(db, KEY, FIXTURE, settings=settings).status == "success"
    product = Product(name="Fixture lamp")
    db.add(product)
    db.flush()
    listing = Listing(
        source_id=1, external_id=uuid4().hex, url="https://example.test", title="Fixture lamp"
    )
    listing.product_id = product.id
    db.add(listing)
    db.flush()
    # The store wrote the UPC as an EAN-13 with a leading zero: one GTIN after M-4.
    db.add(ListingVariant(listing_id=listing.id, external_id="1", barcode="0036000291452"))
    db.flush()
    rows = db.scalars(select(AmazonRank).order_by(AmazonRank.id)).all()
    assert list(link_products(db, rows).values()) == [product.id, None, product.id]
