"""Versioned manual-import columns; downloads carry headers only, never a data row (DEC-191)."""

import csv
import io
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Column:
    kind: Literal[
        "text", "money", "currency", "date", "bool", "int", "interest", "country", "rate", "id"
    ]
    required: bool = False
    default: str = ""


@dataclass(frozen=True)
class Template:
    columns: dict[str, Column]
    template_version: str = "csv-v1"
    one_of: tuple[str, ...] = ()
    # Headers a file must carry even though their cells may be blank (DEC-162).
    required_headers: tuple[str, ...] = ()


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
            "product_id": Column("id"),
            "variant_id": Column("id"),
            "observed_for": Column("date"),
        },
        # Blank compare_at_price means no compare-at; blank available means unknown.
        required_headers=("compare_at_price", "available"),
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
    # Google's download headers, normalized; its Filters line fills the first three (DEC-267).
    "merchant_bestsellers": Template(
        {
            "report_week": Column("date", True),
            "country": Column("country", True),
            "category": Column("text"),
            "popularity_rank": Column("int", True),
            "previous_rank": Column("int"),
            "title": Column("text", True),
            "brand": Column("text"),
            "availability": Column("text"),
            "relative_demand": Column("text"),
            "relative_demand_change": Column("text"),
            "gtins": Column("text"),
            "price_range_min": Column("money"),
            "price_range_max": Column("money"),
            "price_range_currency": Column("currency"),
        }
    ),
}


def template_csv(source_key: str) -> bytes:
    """UTF-8 CSV containing only the header row, so an unchanged download imports nothing."""
    output = io.StringIO(newline="")
    csv.writer(output).writerow(TEMPLATES[source_key].columns)
    return output.getvalue().encode("utf-8")
