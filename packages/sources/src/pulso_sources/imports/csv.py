"""Strict CSV validation and a write-free preview; source adapters classify changes."""

import csv
import io
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from pulso_core.money import CURRENCY_EXPONENTS, to_minor
from pulso_sources.framework import UpsertStats
from pulso_sources.imports.templates import TEMPLATES, Column

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 100_000
csv.field_size_limit(MAX_BYTES)
type Cell = str | int | Decimal | bool | date
type Row = dict[str, Cell]


@dataclass(frozen=True)
class RowError:
    row: int
    column: str
    message: str


class DuplicateEntityRows(ValueError):
    def __init__(self, errors: list[RowError]) -> None:
        super().__init__("Duplicate or inconsistent entity rows in this template")
        self.errors = errors


@dataclass(frozen=True)
class ParsedCSV:
    rows: list[Row]
    errors: list[RowError]
    skipped: int


@dataclass(frozen=True)
class Preview:
    rows: list[Row]
    counts: dict[str, int]
    errors: list[RowError]


def decode_upload(body: bytes) -> str:
    if len(body) > MAX_BYTES:
        raise ValueError("File exceeds 20 MiB")
    return body.decode("utf-8-sig")


def _cell(value: str, column: Column, currency: str) -> Cell:
    if "\x00" in value:
        raise ValueError("NUL characters are not allowed")
    match column.kind:
        case "rate":
            rate = Decimal(value)
            if not rate.is_finite() or not 0 < rate < Decimal("1e10"):
                raise ValueError("Rate must be finite, positive and fit NUMERIC(18,8)")
            if rate != rate.quantize(Decimal("0.00000001")):
                raise ValueError("Rate exceeds eight decimal places")
            return rate
        case "money":
            amount = Decimal(value)
            if to_minor(amount, currency) < 0:
                raise ValueError("Money must be non-negative")
            return amount
        case "currency":
            if value not in CURRENCY_EXPONENTS:
                raise ValueError("Unsupported currency")
        case "date":
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError("Use YYYY-MM-DD")
            return date.fromisoformat(value)
        case "bool":
            if value not in {"true", "false"}:
                raise ValueError("Use true or false")
            return value == "true"
        case "int" | "interest":
            if not re.fullmatch(r"[0-9]+", value):
                raise ValueError("Use a non-negative integer")
            number = int(value)
            if number > (100 if column.kind == "interest" else 2**31 - 1):
                raise ValueError("Integer out of range")
            return number
        case "country":
            if not re.fullmatch(r"[A-Z]{2}", value):
                raise ValueError("Use a two-letter uppercase country code")
    return value


def _entity_errors(source_key: str, rows: dict[int, Row], as_of: date) -> list[RowError]:
    # CSV rows share a listing but can describe distinct variants and freight quotes.
    sku_products = {
        row["sku"]: row["cj_product_id"]
        for row in rows.values()
        if row.get("sku") and row.get("cj_product_id")
    }
    seen: dict[tuple[Cell | None, ...], tuple[int, tuple[Cell | None, ...] | None]] = {}
    errors: dict[int, RowError] = {}
    for line, row in rows.items():
        day = row.get("observed_for", as_of)
        checks: list[tuple[tuple[Cell | None, ...], tuple[Cell | None, ...] | None]] = []
        if source_key == "shopify_stores":
            product: tuple[Cell | None, ...] = (
                "product_url",
                row["store_domain"],
                row["product_url"],
            )
            checks = [
                (product, (row["title"], row["currency"], day)),
                (("sku", *product, row.get("sku") or row.get("variant_title")), None),
            ]
        elif source_key == "cj":
            sku = row.get("sku")
            pid = row.get("cj_product_id")
            if pid is None and sku is not None:
                pid = sku_products.get(sku)
            product = ("cj_product_id", pid) if pid else ("sku", sku)
            checks = [
                (product, (row["name"], row["currency"], row.get("moq", 1), day)),
                (("unit_cost", *product, sku), (row["unit_cost"],)),
                (
                    (
                        "sku" if sku else "cj_product_id",
                        *product,
                        sku,
                        row.get("warehouse_country"),
                    ),
                    None,
                ),
            ]
            if sku and pid:
                checks.append((("cj_product_id", "sku", sku), (pid,)))
        for identity, values in checks:
            prior, prior_values = seen.setdefault(identity, (line, values))
            if prior != line and (values is None or prior_values != values):
                message = "Duplicate entity" if values is None else "Conflicting entity fields"
                for number, other in ((prior, line), (line, prior)):
                    errors.setdefault(
                        number, RowError(number, str(identity[0]), f"{message} with row {other}")
                    )
    return list(errors.values())


def parse_csv(
    source_key: str,
    body: bytes,
    *,
    mapping: Mapping[str, str] | None = None,
    as_of: date | None = None,
) -> ParsedCSV:
    """Mapping is uploaded header -> template column; unknown/duplicate headers fail closed."""
    template = TEMPLATES[source_key]
    text = decode_upload(body)
    as_of = as_of or datetime.now(UTC).date()

    def normalize(name: str) -> str:
        return name.strip().casefold().replace(" ", "_").replace("-", "_")

    aliases = {normalize(k): v for k, v in (mapping or {}).items()}
    try:
        delimiter = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;").delimiter
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = [aliases.get(normalize(h), normalize(h)) for h in next(reader)]
        if len(set(headers)) != len(headers) or any(h not in template.columns for h in headers):
            raise ValueError("Unknown or duplicate mapped columns")
        missing = [
            name
            for name, col in template.columns.items()
            if col.required and not col.default and name not in headers
        ]
        if template.one_of and not any(name in headers for name in template.one_of):
            missing.append(" or ".join(template.one_of))
        if missing:
            raise ValueError("Missing required columns: " + ", ".join(missing))
        rows: dict[int, Row] = {}
        errors, skipped = [], 0
        for count, values in enumerate(reader, 1):
            if count > MAX_ROWS:
                raise ValueError("File exceeds 100,000 rows")
            line = reader.line_num
            if not values or not any(values):
                skipped += 1
                continue
            if len(values) != len(headers):
                errors.append(RowError(line, "", "Row width differs from header"))
                continue
            raw = dict(zip(headers, values, strict=True))
            row: Row = {}
            start = len(errors)
            for name, column in template.columns.items():
                value = raw.get(name, "") or column.default
                if not value.strip():
                    if column.required:
                        errors.append(RowError(line, name, "Required field is missing"))
                    continue
                try:
                    cell = _cell(value, column, raw.get("currency") or "USD")
                    row[name] = cell
                    if isinstance(cell, date) and cell > as_of:
                        errors.append(
                            RowError(line, name, "Date is later than the UTC capture date")
                        )
                except ValueError, KeyError, InvalidOperation:
                    errors.append(RowError(line, name, f"Invalid {column.kind} value"))
            if template.one_of and not any(row.get(name) for name in template.one_of):
                errors.append(
                    RowError(line, " or ".join(template.one_of), "One identifier required")
                )
            minimum, maximum = row.get("min_days"), row.get("max_days")
            if isinstance(minimum, int) and isinstance(maximum, int) and minimum > maximum:
                errors.append(RowError(line, "max_days", "Must be at least min_days"))
            if len(errors) == start:
                rows[line] = row
        duplicates = _entity_errors(source_key, rows, as_of)
        if duplicates:
            raise DuplicateEntityRows(errors + duplicates)
        return ParsedCSV(list(rows.values()), errors, skipped)
    except (csv.Error, StopIteration, IndexError) as exc:
        raise ValueError("Malformed CSV or missing header") from exc


def preview_csv(
    source_key: str,
    body: bytes,
    *,
    classify: Callable[[Sequence[Row]], UpsertStats],
    mapping: Mapping[str, str] | None = None,
    as_of: date | None = None,
) -> Preview:
    """classify must be read-only and account for every valid row; never calls upsert."""
    try:
        parsed = parse_csv(source_key, body, mapping=mapping, as_of=as_of)
    except DuplicateEntityRows as exc:
        return Preview(
            [],
            {"insert": 0, "update": 0, "skip": 0, "invalid": len({e.row for e in exc.errors})},
            exc.errors,
        )
    stats = classify(parsed.rows)
    counts = {"insert": stats.inserted, "update": stats.updated, "skip": stats.unchanged}
    if min(counts.values()) < 0 or sum(counts.values()) != len(parsed.rows):
        raise ValueError("Classifier must account for every valid row")
    counts["skip"] += parsed.skipped
    counts["invalid"] = len({error.row for error in parsed.errors})
    return Preview(parsed.rows[:20], counts, parsed.errors)
