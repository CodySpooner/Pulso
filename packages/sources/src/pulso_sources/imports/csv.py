"""Strict CSV validation and a write-free preview; source adapters classify changes."""

import csv
import io
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
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


def parse_csv(
    source_key: str, body: bytes, *, mapping: Mapping[str, str] | None = None
) -> ParsedCSV:
    """Mapping is uploaded header -> template column; unknown/duplicate headers fail closed."""
    template = TEMPLATES[source_key]
    text = decode_upload(body)

    def normalize(name: str) -> str:
        return name.strip().casefold().replace(" ", "_").replace("-", "_")

    aliases = {normalize(k): v for k, v in (mapping or {}).items()}
    try:
        dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;")
        reader = csv.reader(io.StringIO(text, newline=""), dialect, strict=True)
        headers = [aliases.get(normalize(h), normalize(h)) for h in next(reader)]
        if len(set(headers)) != len(headers) or any(h not in template.columns for h in headers):
            raise ValueError("Unknown or duplicate mapped columns")
        rows, errors, skipped = [], [], 0
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
                    row[name] = _cell(value, column, raw.get("currency") or "USD")
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
                rows.append(row)
        return ParsedCSV(rows, errors, skipped)
    except (csv.Error, StopIteration, IndexError) as exc:
        raise ValueError("Malformed CSV or missing header") from exc


def preview_csv(
    source_key: str,
    body: bytes,
    *,
    classify: Callable[[Sequence[Row]], UpsertStats],
    mapping: Mapping[str, str] | None = None,
) -> Preview:
    """classify must be read-only and account for every valid row; never calls upsert."""
    parsed = parse_csv(source_key, body, mapping=mapping)
    stats = classify(parsed.rows)
    counts = {"insert": stats.inserted, "update": stats.updated, "skip": stats.unchanged}
    if min(counts.values()) < 0 or sum(counts.values()) != len(parsed.rows):
        raise ValueError("Classifier must account for every valid row")
    counts["skip"] += parsed.skipped
    counts["invalid"] = len({error.row for error in parsed.errors})
    return Preview(parsed.rows[:20], counts, parsed.errors)
