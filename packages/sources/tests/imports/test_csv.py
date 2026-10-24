import csv
import io
from datetime import date
from decimal import Decimal
from typing import Literal

import pytest

from pulso_sources.framework import UpsertStats
from pulso_sources.imports import csv as imports_csv
from pulso_sources.imports.csv import DuplicateEntityRows, parse_csv, preview_csv
from pulso_sources.imports.templates import TEMPLATES, template_csv

from .conftest import sample_csv


@pytest.mark.parametrize("source", TEMPLATES)
def test_template_download_is_header_only(source: str) -> None:
    body = template_csv(source)
    assert list(csv.reader(io.StringIO(body.decode()))) == [list(TEMPLATES[source].columns)]
    parsed = parse_csv(source, body)
    assert parsed.rows == [] and parsed.errors == [] and parsed.skipped == 0
    assert TEMPLATES[source].template_version == "csv-v1"


@pytest.mark.parametrize("source", TEMPLATES)
def test_every_sample_fixture_is_one_valid_row(source: str) -> None:
    parsed = parse_csv(source, sample_csv(source))
    assert len(parsed.rows) == 1 and parsed.errors == [] and parsed.skipped == 0


@pytest.mark.parametrize(
    "rate", ["not-a-number", "0", "-1", "0.123456789", "1e10", "NaN", "Infinity"]
)
def test_invalid_rate_explains_valid_form_once_per_cell(rate: str) -> None:
    parsed = parse_csv(
        "fx_frankfurter", f"date,base,quote,rate\n2026-01-01,USD,JPY,{rate}\n".encode()
    )
    assert parsed.rows == []
    assert [(error.row, error.column, error.message) for error in parsed.errors] == [
        (
            2,
            "rate",
            "Invalid rate. Use a finite positive decimal number below 10,000,000,000 "
            "with up to 8 decimal places.",
        )
    ]


@pytest.mark.parametrize(
    "rate", ["150", "0.00000001", "9999999999.99999999", "1.230000000", "1e-8"]
)
def test_valid_rate_is_preserved(rate: str) -> None:
    parsed = parse_csv(
        "fx_frankfurter", f"date,base,quote,rate\n2026-01-01,USD,JPY,{rate}\n".encode()
    )
    assert parsed.errors == []
    assert len(parsed.rows) == 1
    assert parsed.rows[0]["rate"] == Decimal(rate)


def test_bom_semicolon_mapping_defaults_and_exact_money() -> None:
    body = (
        "\ufeffStore;URL;Name;Cost;available;compare_at_price\n"
        'example.com;https://example.com/p;"Café; mug";19.99;false;\n'
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
        # imp-151 (XR-4): commit needs canonical positive BIGINT Shopify IDs.
        *(
            (column, value)
            for column in ("product_id", "variant_id")
            for value in ("abc", "0", "0012", "12.0", "-1", str(2**63))
        ),
    ],
)
def test_invalid_values_are_not_repaired(column: str, value: str) -> None:
    rows = list(csv.DictReader(io.StringIO(sample_csv("shopify_stores").decode())))
    rows[0][column] = value
    output = io.StringIO()
    writer = csv.DictWriter(output, rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_csv("shopify_stores", output.getvalue().encode())
    assert parsed.rows == []
    assert column in {error.column for error in parsed.errors}


def test_shopify_ids_up_to_bigint_stay_exact_text() -> None:
    rows = list(csv.DictReader(io.StringIO(sample_csv("shopify_stores").decode())))
    rows[0] |= {"product_id": str(2**63 - 1), "variant_id": "7"}
    output = io.StringIO()
    writer = csv.DictWriter(output, rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    parsed = parse_csv("shopify_stores", output.getvalue().encode())
    assert parsed.errors == []
    assert (parsed.rows[0]["product_id"], parsed.rows[0]["variant_id"]) == (str(2**63 - 1), "7")


def test_cj_moq_below_one_is_a_preview_row_error() -> None:
    """imp-151 (XR-3): commit requires a positive moq, so preview flags 0 on its row."""
    body = b"sku,name,unit_cost,moq\nA,Example,1,0\nB,Example,1,1\n"
    preview = preview_csv("cj", body, classify=lambda rows: UpsertStats(inserted=len(rows)))
    assert [(e.row, e.column) for e in preview.errors] == [(2, "moq")]
    assert (preview.counts["insert"], preview.counts["invalid"]) == (1, 1)


def test_cj_alternative_identifier_and_delivery_bounds() -> None:
    parsed = parse_csv(
        "cj", b"sku,name,unit_cost,min_days,max_days\nSKU,Example,1,3,7\n,Example,2,7,3\n"
    )
    assert len(parsed.rows) == 1
    assert {error.column for error in parsed.errors} == {"cj_product_id or sku", "max_days"}


@pytest.mark.parametrize(
    "identifiers,column",
    [("P,A\nP,A", "sku"), ("P,A\n,A", "sku"), (",A\n,A", "sku")],
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


@pytest.mark.parametrize("delimiter", [",", ";"])
@pytest.mark.parametrize("quoting", [csv.QUOTE_MINIMAL, csv.QUOTE_ALL])
def test_excel_quoted_fields_round_trip(delimiter: str, quoting: Literal[0, 1]) -> None:
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=delimiter, quoting=quoting)
    writer.writerow(["keyword", "date", "interest"])
    titles = ['Lamp 12" Brass', 'Double "" quotes', 'Lamp 12", brass; gold\nNew line']
    writer.writerows((title, "2026-01-01", 50) for title in titles)
    parsed = parse_csv("google_trends", output.getvalue().encode())
    assert not parsed.errors
    assert [row["keyword"] for row in parsed.rows] == titles


@pytest.mark.parametrize(
    "source,body",
    [
        (
            "shopify_stores",
            b"store_domain,product_url,title,price,sku,variant_title,compare_at_price,available\n"
            b"a.test,/tee,Tee,10,TEE-S,S,,\na.test,/tee,Tee,12,TEE-M,M,,\n",
        ),
        (
            "shopify_stores",
            b"store_domain,product_url,title,price,variant_title,compare_at_price,available\n"
            b"a.test,/tee,Tee,10,S,,\na.test,/tee,Tee,12,M,,\n",
        ),
        (
            "cj",
            b"cj_product_id,sku,name,unit_cost,warehouse_country,ship_cost_us\n"
            b"P1,S1,Tee,5,CN,3\nP1,S1,Tee,5,US,1\n",
        ),
        ("cj", b"cj_product_id,sku,name,unit_cost\nP1,S1,Tee,5\nP1,S2,Tee,6\n"),
        (
            "cj",
            b"cj_product_id,sku,name,unit_cost,warehouse_country\nP1,S1,Tee,5,CN\n,S1,Tee,5,US\n",
        ),
    ],
)
def test_distinct_variants_and_warehouses_are_valid(source: str, body: bytes) -> None:
    parsed = parse_csv(source, body)
    assert len(parsed.rows) == 2 and not parsed.errors


@pytest.mark.parametrize(
    "changes",
    [
        {"unit_cost": "6"},
        {"name": "Other"},
        {"observed_for": "2026-01-02"},
        {"cj_product_id": "OTHER"},
    ],
)
def test_cj_warehouse_rows_cannot_conflict_on_shared_entities(changes: dict[str, str]) -> None:
    example = next(csv.DictReader(io.StringIO(sample_csv("cj").decode())))
    output = io.StringIO()
    writer = csv.DictWriter(output, example.keys())
    writer.writeheader()
    writer.writerows([example, {**example, "warehouse_country": "CN", **changes}])
    with pytest.raises(DuplicateEntityRows) as caught:
        parse_csv("cj", output.getvalue().encode())
    assert {e.row for e in caught.value.errors} == {2, 3}


def test_implicit_and_explicit_capture_day_match_across_variants() -> None:
    body = (
        b"store_domain,product_url,title,price,sku,observed_for,compare_at_price,available\n"
        b"a.test,/tee,Tee,10,S,2026-01-01,,\na.test,/tee,Tee,12,M,,,\n"
    )
    assert len(parse_csv("shopify_stores", body, as_of=date(2026, 1, 1)).rows) == 2


@pytest.mark.parametrize(
    "column,value", [("title", "Other"), ("currency", "EUR"), ("observed_for", "2026-01-02")]
)
def test_shopify_variants_require_consistent_listing_fields(column: str, value: str) -> None:
    example = next(csv.DictReader(io.StringIO(sample_csv("shopify_stores").decode())))
    output = io.StringIO()
    writer = csv.DictWriter(output, example.keys())
    writer.writeheader()
    writer.writerows([example, {**example, "sku": "OTHER", column: value}])
    with pytest.raises(DuplicateEntityRows) as caught:
        parse_csv("shopify_stores", output.getvalue().encode())
    assert {e.row for e in caught.value.errors} == {2, 3}


@pytest.mark.parametrize(
    "source,body,missing",
    [
        ("google_trends", b"keyword,date\na,2026-01-01\n", "interest"),
        ("cj", b"name,unit_cost\nTee,5\n", "cj_product_id or sku"),
        ("shopify_stores", b"store_domain,product_url,title\na.test,/tee,Tee\n", "price"),
        (
            "shopify_stores",
            b"store_domain,product_url,title,price\na.test,/tee,Tee,1\n",
            "compare_at_price, available",
        ),
    ],
)
def test_missing_headers_fail_before_reading_rows(
    source: str, body: bytes, missing: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(imports_csv, "MAX_ROWS", 0)
    with pytest.raises(ValueError, match=missing):
        parse_csv(source, body)


@pytest.mark.parametrize(
    "source,column",
    [("google_trends", "date"), ("shopify_stores", "observed_for"), ("cj", "observed_for")],
)
def test_future_dates_are_row_errors(source: str, column: str) -> None:
    body = sample_csv(source)
    parsed = parse_csv(source, body, as_of=date(2025, 12, 31))
    assert not parsed.rows and [(e.row, e.column) for e in parsed.errors] == [(2, column)]
    assert "capture" in parsed.errors[0].message
    assert len(parse_csv(source, body, as_of=date(2026, 1, 1)).rows) == 1


def test_distinct_entities_and_trends_dates_remain_importable() -> None:
    for source, body in [
        ("cj", b"cj_product_id,sku,name,unit_cost\nP,,One,1\n,P,Two,2\n"),
        (
            "shopify_stores",
            b"store_domain,product_url,title,price,compare_at_price,available\n"
            b"a.test,/p,One,1,,\nb.test,/p,Two,2,,\n",
        ),
        ("google_trends", b"keyword,date,interest\na,2026-10-01,1\na,2026-10-02,2\n"),
        ("fx_frankfurter", b"date,base,quote,rate\n2026-01-01,USD,JPY,150\n2026-01-01,USD,EUR,1\n"),
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


def test_duplicate_fx_pair_date_names_both_rows() -> None:
    # P1-40 L1: preview must reject what the Frankfurter parser would refuse at commit.
    body = b"date,base,quote,rate\n2026-01-01,USD,JPY,150\n2026-01-01,USD,JPY,151\n"
    with pytest.raises(DuplicateEntityRows) as caught:
        parse_csv("fx_frankfurter", body)
    assert {(e.row, e.message) for e in caught.value.errors} == {
        (2, "Duplicate entity with row 3"),
        (3, "Duplicate entity with row 2"),
    }


@pytest.mark.parametrize(
    "header,message",
    [
        ("keyword,date,interest,Notes", "Unknown columns: notes$"),
        ("keyword,Keyword,date,interest", "Duplicate columns: keyword$"),
        ("keyword,,date,interest", r"Unknown columns: \(blank\)$"),
    ],
)
def test_header_errors_name_the_columns(header: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_csv("google_trends", f"{header}\na,x,2026-01-01,1\n".encode())


def test_trailing_unnamed_empty_column_is_ignored() -> None:
    # Spreadsheet exports often end every line with a delimiter.
    body = b"keyword,date,interest,\na,2026-01-01,1,\nb,2026-01-02,2\nc,2026-01-03,3,x\n"
    parsed = parse_csv("google_trends", body)
    assert [row["keyword"] for row in parsed.rows] == ["a", "b"]
    assert [(e.row, e.message) for e in parsed.errors] == [(4, "Row width differs from header")]


def test_file_and_row_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    body = sample_csv("google_trends")
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
