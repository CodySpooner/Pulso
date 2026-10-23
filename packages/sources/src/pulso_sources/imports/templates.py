"""Versioned manual-import columns; downloads carry headers only, never a data row (DEC-191)."""

import csv
import io
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Column:
    kind: Literal["text", "money", "currency", "date", "bool", "int", "interest", "country", "rate"]
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
            "store_domain": Column("text", True),
            "product_url": Column("text", True),
            "title": Column("text", True),
            "price": Column("money", True),
            "currency": Column("currency", default="USD"),
            "compare_at_price": Column("money"),
            "available": Column("bool"),
            "variant_title": Column("text"),
            "sku": Column("text"),
            "observed_for": Column("date"),
        }
    ),
    "cj": Template(
        {
            "cj_product_id": Column("text"),
            "sku": Column("text"),
            "name": Column("text", True),
            "unit_cost": Column("money", True),
            "currency": Column("currency", default="USD"),
            "warehouse_country": Column("country"),
            "ship_cost_us": Column("money"),
            "min_days": Column("int"),
            "max_days": Column("int"),
            "moq": Column("int"),
            "observed_for": Column("date"),
        },
        one_of=("cj_product_id", "sku"),
    ),
    "google_trends": Template(
        {
            "keyword": Column("text", True),
            "date": Column("date", True),
            "interest": Column("interest", True),
            "geo": Column("country", default="US"),
            "source": Column("text"),
        }
    ),
    "fx_frankfurter": Template(
        {
            "date": Column("date", True),
            "base": Column("currency", True),
            "quote": Column("currency", True),
            "rate": Column("rate", True),
        }
    ),
}


def template_csv(source_key: str) -> bytes:
    """UTF-8 CSV containing only the header row, so an unchanged download imports nothing."""
    output = io.StringIO(newline="")
    csv.writer(output).writerow(TEMPLATES[source_key].columns)
    return output.getvalue().encode("utf-8")
