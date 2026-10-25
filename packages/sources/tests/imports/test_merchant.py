"""Merchant Center Popular products CSV (p2-29, DEC-267). Every row here is synthetic."""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from pulso_core.models import Listing, ListingVariant, PopularProduct, Product, RawPayload
from pulso_core.settings import Settings
from pulso_sources.framework import UpsertStats
from pulso_sources.imports import ADAPTERS, ImportData, commit_import, parse_csv
from pulso_sources.imports.csv import DuplicateEntityRows, RowError
from pulso_sources.merchant_bestsellers import ImportAdapter, link_products

KEY = "merchant_bestsellers"


def gtin(body: str) -> str:
    """body plus its GS1 mod-10 check digit."""
    weighted = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return body + str(-weighted % 10)


GOOD, OTHER = gtin("590123412345"), gtin("761234567890")
BAD = GOOD[:-1] + str((int(GOOD[-1]) + 1) % 10)  # a wrong check digit
# Google's layout: a Name line, a Filters line, then the table (header names only, p2-29).
GOOGLE = (
    "Name: Products and brands customers are buying on Google\r\n"
    '"Filters: Country = US; Category = Home & Garden > Lighting; Time period = W20260105; '
    'Availability = In stock, Product suggestion"\r\n'
    "Popularity rank,Title,Brand,Availability,Price Range Min,Price Range Max,"
    "Price Range Currency,GTINs\r\n"
    f"1,Example desk lamp,Example Brand,In stock,20,35,USD,{GOOD} {OTHER}\r\n"
    "2,Example floor lamp,,Product suggestion,,,,\r\n"
    f"3,Example lamp with a bad code,Example Brand,Product suggestion,10,12,USD,{BAD}\r\n"
).encode()


def test_google_download_parses_with_its_filters_as_columns() -> None:
    parsed = parse_csv(KEY, GOOGLE)
    assert parsed.errors == [] and len(parsed.rows) == 3
    assert parsed.rows[0] == {
        "report_week": date(2026, 1, 5),
        "country": "US",
        "category": "Home & Garden > Lighting",
        "popularity_rank": 1,
        "title": "Example desk lamp",
        "brand": "Example Brand",
        "availability": "In stock",
        "gtins": f"{GOOD} {OTHER}",
        "price_range_min": Decimal(20),
        "price_range_max": Decimal(35),
        "price_range_currency": "USD",
    }
    rows = ImportAdapter(ImportData("csv", parsed, None)).parse(b"")
    assert rows[1].brand is None and rows[1].price_range_currency is None


def test_renamed_columns_import_through_the_mapping_step() -> None:
    body = f"Week,Country,Rank,Product title,Barcodes\r\n2026-01-05,US,7,Example,{GOOD}\r\n"
    mapping = {
        "Week": "report_week",
        "Rank": "popularity_rank",
        "Product title": "title",
        "Barcodes": "gtins",
    }
    parsed = parse_csv(KEY, body.encode(), mapping=mapping)
    assert parsed.errors == []
    assert parsed.rows == [
        {
            "report_week": date(2026, 1, 5),
            "country": "US",
            "popularity_rank": 7,
            "title": "Example",
            "gtins": GOOD,
        }
    ]
    with pytest.raises(ValueError, match="Unknown columns: week, rank"):
        parse_csv(KEY, body.encode())


def test_only_weekly_reports_on_their_monday_with_one_row_per_rank() -> None:
    with pytest.raises(ValueError, match="weekly report"):
        parse_csv(KEY, GOOGLE.replace(b"W20260105", b"M202601"))
    tuesday = b"report_week,country,popularity_rank,title\r\n2026-01-06,US,1,Example\r\n"
    assert parse_csv(KEY, tuesday).errors == [
        RowError(2, "report_week", "Use the Monday that starts the week")
    ]
    with pytest.raises(DuplicateEntityRows):
        parse_csv(KEY, GOOGLE.replace(b"\r\n2,", b"\r\n1,"))


@pytest.fixture
def db(db_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.setitem(ADAPTERS, KEY, ImportAdapter)  # conftest swaps in FakeAdapter
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.mark.db
def test_reimporting_the_same_download_writes_no_new_rows(
    db: Session, settings: Settings, s3: MagicMock
) -> None:
    first = commit_import(db, KEY, GOOGLE, settings=settings)
    assert (first.status, first.rows_inserted) == ("success", 3), first.error_message
    again = commit_import(db, KEY, GOOGLE, settings=settings)
    assert again.status == "skipped" and again.params["original_run_id"] == first.id
    rows = db.scalars(select(PopularProduct).order_by(PopularProduct.rank)).all()
    assert [(row.rank, row.title) for row in rows] == [
        (1, "Example desk lamp"),
        (2, "Example floor lamp"),
        (3, "Example lamp with a bad code"),
    ]
    top = rows[0]
    assert (top.observed_for, top.country, top.category) == (
        date(2026, 1, 5),
        "US",
        "Home & Garden > Lighting",
    )
    assert (top.price_min_minor, top.price_max_minor, top.currency) == (2000, 3500, "USD")
    assert (rows[1].brand, rows[1].price_min_minor, rows[1].currency) == (None, None, None)
    assert top.raw_payload_id == first.params["raw_payload_id"]
    assert top.captured_at.date() == datetime.now(UTC).date()
    # The capture parsed again by the same parser meets the unique key and adds nothing.
    payload = db.get_one(RawPayload, top.raw_payload_id)
    adapter = ImportAdapter(ImportData("csv", parse_csv(KEY, GOOGLE), None))
    stats = adapter.upsert(db, adapter.parse(b""), payload, parser_version=adapter.parser_version)
    assert stats == UpsertStats(inserted=0, unchanged=3)
    assert db.scalar(select(func.count()).select_from(PopularProduct)) == 3


@pytest.mark.db
def test_rows_link_to_one_live_product_by_valid_gtin(
    db: Session, settings: Settings, s3: MagicMock
) -> None:
    assert commit_import(db, KEY, GOOGLE, settings=settings).status == "success"

    def product(barcode: str, merged_into: UUID | None = None) -> UUID:
        row = Product(name="Fixture", merged_into_id=merged_into)
        db.add(row)
        db.flush()
        listing = Listing(
            source_id=1, external_id=uuid4().hex, url="https://example.test", title="Fixture"
        )
        listing.product_id = row.id
        db.add(listing)
        db.flush()
        db.add(ListingVariant(listing_id=listing.id, external_id=uuid4().hex, barcode=barcode))
        db.flush()
        return row.id

    live = product(f"0{GOOD[:4]}-{GOOD[4:]}")  # GTIN-14 with a dash: one code after M-4
    product(OTHER, merged_into=live)  # follows the merge to the live product
    product(BAD)  # an identical raw string with a wrong check digit never links
    rows = db.scalars(select(PopularProduct).order_by(PopularProduct.rank)).all()
    assert list(link_products(db, rows).values()) == [live, None, None]
    product(GOOD)  # the same GTIN on a second live product: ambiguous, so unlinked
    assert link_products(db, rows)[rows[0].id] is None
