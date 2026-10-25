"""M-6 coverage: the existing fixture products through each adapter's parse(), then the mapper."""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core import taxonomy
from pulso_core.models import Listing, Product
from pulso_sources import cj
from pulso_sources.shopify_stores import records

FIXTURES = Path(__file__).parent
SHOPIFY, CJ = 1, 2  # sources rows from migration 0001


def fixture_listings() -> dict[tuple[int, str], tuple[str | None, str]]:
    """Each distinct fixture product: (source id, external id) -> (product_type, title)."""
    found: dict[tuple[int, str], tuple[str | None, str]] = {}
    for name in ("normal", "page_1", "page_2"):
        body = json.loads((FIXTURES / "shopify_stores" / "fixtures" / f"{name}.json").read_text())
        for item in records.parse(json.dumps(body["body"]).encode()):
            assert isinstance(item, records.Product)
            found[SHOPIFY, str(item.id)] = (item.product_type, item.title)
    for record in cj.parse((FIXTURES / "cj" / "fixtures" / "list_v2.json").read_bytes()):
        found[CJ, record.external_id] = (None, record.title)  # CJ stores no category yet
    return found


def test_at_least_90_percent_of_fixture_products_get_a_category(db_engine: Engine) -> None:
    listings = fixture_listings()
    with Session(db_engine) as session, session.begin():
        taxonomy.load(session)
        for (source_id, external_id), (product_type, title) in listings.items():
            product = Product(name=title)
            session.add(product)
            session.flush()
            session.add(
                Listing(
                    source_id=source_id,
                    external_id=external_id,
                    url="https://example.test/",
                    title=title,
                    product_type=product_type,
                    product_id=product.id,
                )
            )
        counts = taxonomy.apply(session)
        rows = session.execute(select(Product.category_id, Product.category_source)).all()
    categorised = [row for row in rows if row.category_id is not None]
    assert len(rows) == len(listings) == 253
    assert len(categorised) / len(rows) >= 0.9
    assert {row.category_source for row in categorised} == {"rule"}
    assert all(row.category_source is None for row in rows if row.category_id is None)
    assert counts["categorised"] == len(categorised) == 252  # "Fixture bowl" stays NULL
