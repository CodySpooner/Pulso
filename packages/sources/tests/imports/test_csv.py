import csv
import io
from datetime import date
from decimal import Decimal

import pytest

from pulso_sources.framework import UpsertStats
from pulso_sources.imports import csv as imports_csv
from pulso_sources.imports.csv import DuplicateEntityRows, parse_csv, preview_csv
from pulso_sources.imports.templates import TEMPLATES, template_csv


@pytest.mark.parametrize("source", TEMPLATES)
def test_every_template_validates_its_example(source: str) -> None:
    parsed = parse_csv(source, template_csv(source))
    assert len(parsed.rows) == 1 and parsed.errors == [] and parsed.skipped == 0
    assert TEMPLATES[source].template_version == "csv-v1"


def test_bom_semicolon_mapping_defaults_and_exact_money() -> None:
    body = (
        "\ufeffStore;URL;Name;Cost;available\n"
        'example.com;https://example.com/p;"Café; mug";19.99;false\n'
    )
    parsed = parse_csv(
        "shopify_stores",
        body.encode(),
        mapping={
            "Store": "store_domain",
            "URL": "product_url",
            "Name": "title",
            "Cost": "price",
        },
    )
    assert not parsed.errors
    assert parsed.rows[0]["title"] == "Café; mug"
    assert parsed.rows[0]["price"] == Decimal("19.99")
    assert parsed.rows[0]["currency"] == "USD"
    assert parsed.rows[0]["available"] is False


def test_errors_skip_whole_rows_and_preview_uses_source_classification() -> None:
    body = (
        b"keyword,date,interest\na,2026-01-01,50\nb,2026-02-30,101\n"
        b"c,2026-01-02,20\n\nwrong,width\n"
    )
    preview = preview_csv(
        "google_trends", body, classify=lambda rows: UpsertStats(inserted=1, updated=1)
    )
    assert [row["keyword"] for row in preview.rows] == ["a", "c"]
    assert preview.rows[0]["date"] == date(2026, 1, 1)
    assert preview.counts == {"insert": 1, "update": 1, "skip": 1, "invalid": 2}
    assert {(error.row, error.column) for error in preview.errors} == {
        (3, "date"),
        (3, "interest"),
        (6, ""),
    }
    assert all(error.message for error in preview.errors)


def test_preview_limits_rows_but_counts_the_entire_file() -> None:
    body = b"keyword,date,interest\n" + b"example,2026-01-01,10\n" * 25
    preview = preview_csv(
        "google_trends", body, classify=lambda rows: UpsertStats(unchanged=len(rows))
    )
    assert len(preview.rows) == 20 and preview.counts["skip"] == 25
    with pytest.raises(ValueError, match="account for every"):
        preview_csv("google_trends", body, classify=lambda _: UpsertStats())


@pytest.mark.parametrize(
    "column,value",
    [
        ("price", "NaN"),
        ("price", "Infinity"),
        ("price", "0.001"),
        ("price", "-1"),
        ("price", "92233720368547758.08"),
        ("currency", "ZZZ"),
        ("currency", "usd"),
        ("title", ""),
        ("title", "bad\x00title"),
        ("available", "1"),
        ("observed_for", "20260101"),
    ],
)
def test_invalid_values_are_not_repaired(column: str, value: str) -> None:
    rows = list(csv.DictReader(io.StringIO(template_csv("shopify_stores").decode())))
    rows[0][column] = value
    output = io.StringIO()
    writer = csv.DictWriter(output, rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_csv("shopify_stores", output.getvalue().encode())
    assert parsed.rows == []
    assert column in {error.column for error in parsed.errors}


def test_cj_alternative_identifier_and_delivery_bounds() -> None:
    parsed = parse_csv(
        "cj", b"sku,name,unit_cost,min_days,max_days\nSKU,Example,1,3,7\n,Example,2,7,3\n"
    )
    assert len(parsed.rows) == 1
    assert {error.column for error in parsed.errors} == {"cj_product_id or sku", "max_days"}


@pytest.mark.parametrize(
    "identifiers,column",
    [("P,A\nP,B", "cj_product_id"), ("P,A\n,A", "sku"), (",A\n,A", "sku")],
)
def test_duplicate_cj_identifiers_reject_even_without_dates(identifiers: str, column: str) -> None:
    body = "cj_product_id,sku,name,unit_cost\n" + "".join(
        f"{ids},Example,1\n" for ids in identifiers.splitlines()
    )
    with pytest.raises(DuplicateEntityRows) as caught:
        parse_csv("cj", body.encode())
    assert {(e.row, e.column, e.message) for e in caught.value.errors} == {
        (2, column, "Duplicate entity with row 3"),
        (3, column, "Duplicate entity with row 2"),
    }


def test_distinct_entities_and_trends_dates_remain_importable() -> None:
    for source, body in [
        ("cj", b"cj_product_id,sku,name,unit_cost\nP,,One,1\n,P,Two,2\n"),
        (
            "shopify_stores",
            b"store_domain,product_url,title,price\na.test,/p,One,1\nb.test,/p,Two,2\n",
        ),
        ("google_trends", b"keyword,date,interest\na,2026-10-01,1\na,2026-10-02,2\n"),
    ]:
        parsed = parse_csv(source, body)
        assert len(parsed.rows) == 2 and not parsed.errors


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"\xff",
        b"keyword,date,interest,extra\na,2026-01-01,1,x",
        b"keyword,Keyword,date,interest\na,b,2026-01-01,1",
        b'keyword,date,interest\n"unterminated,2026-01-01,1',
    ],
)
def test_file_level_errors(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse_csv("google_trends", body)


def test_file_and_row_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    body = template_csv("google_trends")
    monkeypatch.setattr(imports_csv, "MAX_BYTES", len(body) - 1)
    with pytest.raises(ValueError, match="20 MiB"):
        parse_csv("google_trends", body)
    monkeypatch.setattr(imports_csv, "MAX_BYTES", len(body))
    monkeypatch.setattr(imports_csv, "MAX_ROWS", 0)
    with pytest.raises(ValueError, match="100,000"):
        parse_csv("google_trends", body)


def test_long_text_is_limited_by_upload_cap_not_csv_default() -> None:
    title = "x" * 150_000
    parsed = parse_csv("google_trends", f"keyword,date,interest\n{title},2026-01-01,50\n".encode())
    assert not parsed.errors and parsed.rows[0]["keyword"] == title
