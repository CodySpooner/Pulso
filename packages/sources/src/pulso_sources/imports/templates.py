"""Versioned manual-import columns; example values are download instructions, not seeds."""

import csv
import io
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Column:
    kind: Literal["text", "money", "currency", "date", "bool", "int", "interest", "country", "rate"]
    example: str
    required: bool = False
    default: str = ""


@dataclass(frozen=True)
class Template:
    columns: dict[str, Column]
    template_version: str = "csv-v1"
    one_of: tuple[str, ...] = ()


TEMPLATES = {
    "shopify_stores": Template(
        {
            "store_domain": Column("text", "example.com", True),
            "product_url": Column("text", "https://example.com/products/example", True),
            "title": Column("text", "Example only", True),
            "price": Column("money", "19.99", True),
            "currency": Column("currency", "USD", default="USD"),
            "compare_at_price": Column("money", "24.99"),
            "available": Column("bool", "true"),
            "variant_title": Column("text", "Example variant"),
            "sku": Column("text", "EXAMPLE"),
            "observed_for": Column("date", "2026-01-01"),
        }
    ),
    "cj": Template(
        {
            "cj_product_id": Column("text", "EXAMPLE-ID"),
            "sku": Column("text", "EXAMPLE-SKU"),
            "name": Column("text", "Example only", True),
            "unit_cost": Column("money", "5.00", True),
            "currency": Column("currency", "USD", default="USD"),
            "warehouse_country": Column("country", "US"),
            "ship_cost_us": Column("money", "3.00"),
            "min_days": Column("int", "3"),
            "max_days": Column("int", "7"),
            "moq": Column("int", "1"),
            "observed_for": Column("date", "2026-01-01"),
        },
        one_of=("cj_product_id", "sku"),
    ),
    "google_trends": Template(
        {
            "keyword": Column("text", "example keyword", True),
            "date": Column("date", "2026-01-01", True),
            "interest": Column("interest", "50", True),
            "geo": Column("country", "US", default="US"),
            "source": Column("text", "manual"),
        }
    ),
    "fx_frankfurter": Template(
        {
            "date": Column("date", "2026-01-01", True),
            "base": Column("currency", "USD", True),
            "quote": Column("currency", "JPY", True),
            "rate": Column("rate", "150", True),
        }
    ),
}


def template_csv(source_key: str) -> bytes:
    """UTF-8 CSV containing headers and one explicitly illustrative row."""
    columns = TEMPLATES[source_key].columns
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(columns)
    writer.writerow(column.example for column in columns.values())
    return output.getvalue().encode("utf-8")
