"""Golden vectors (R-16, DEC-265): landed_cost(), its SQL twin and workspace_product_economics
must give the same lines, totals, `complete` and `missing` for every vector."""

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.landed_cost import Amount, Inputs, landed_cost
from pulso_core.landed_cost_loader import STOCK_ENDPOINT, Provenance, calculate, stocked, unit_cost
from pulso_core.models import (
    CollectorRun,
    FxRate,
    Listing,
    ListingSnapshot,
    ListingVariant,
    Product,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    Workspace,
    WorkspaceSettings,
    workspace_product_economics,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "landed_cost_vectors.json").read_text())[
    "vectors"
]
SHOPIFY, CJ, FX = 1, 2, 4  # seeded source ids
PRICED = datetime(2026, 10, 23, 23, 30, tzinfo=UTC)  # store price and freight
COSTED = datetime(2026, 10, 13, 12, tzinfo=UTC)  # supplier cost: its FX rate is 10 days older
SETTINGS = {  # Inputs field: its settings column
    "duty_bps": "duty_default_bps",
    "customs_fee_minor": "customs_fee_minor",
    "payment_fee_bps": "payment_fee_bps",
    "payment_fee_fixed_minor": "payment_fee_fixed_minor",
    "shopify_fee_bps": "shopify_fee_bps",
    "returns_bps": "returns_bps",
    "ad_cost_minor": "default_cpa_minor",
}


def inputs(vector: dict[str, Any]) -> Inputs:
    raw = dict(vector["inputs"])
    for name in ("unit_cost", "freight"):
        if (amount := raw[name]) is not None:
            rate = amount["usd_rate"]
            raw[name] = Amount(amount["minor"], amount["currency"], rate and Decimal(rate))
    return Inputs(**raw | {"estimates": tuple(raw["estimates"])})


def result(cost: Any) -> dict[str, Any]:
    """The compared fields: every line and total, `complete` and `missing` (not `estimates`)."""
    row = dict(cost)
    return {key: list(row[key]) if key == "missing" else row[key] for key in TOTALS}


TOTALS = [key for key in VECTORS[0]["expected"] if key != "estimates"]


@pytest.mark.parametrize("vector", VECTORS, ids=[vector["name"] for vector in VECTORS])
def test_landed_cost_matches_the_golden_vector(vector: dict[str, Any]) -> None:
    cost = asdict(landed_cost(inputs(vector)))
    assert result(cost) == result(vector["expected"])
    assert list(cost["estimates"]) == vector["expected"]["estimates"]


@pytest.mark.db
def test_the_sql_twin_matches_every_golden_vector(db_engine: Engine) -> None:
    wrong = {}
    with db_engine.connect() as connection:
        for vector in VECTORS:
            values = vector["inputs"]
            unit, freight = values["unit_cost"] or {}, values["freight"] or {}
            row = connection.execute(
                text(
                    "SELECT * FROM landed_cost(CAST(:price AS bigint), CAST(:unit AS bigint), "
                    ":unit_currency, CAST(:unit_rate AS numeric), CAST(:freight AS bigint), "
                    ":freight_currency, CAST(:freight_rate AS numeric), CAST(:duty AS integer), "
                    ":quantity, :ddp, CAST(:customs AS bigint), :payment_bps, "
                    "CAST(:payment_fixed AS bigint), :shopify_bps, :returns_bps, "
                    "CAST(:ad_cost AS bigint), :freight_gap)"
                ),
                {
                    "price": values["price_minor"],
                    "unit": unit.get("minor"),
                    "unit_currency": unit.get("currency"),
                    "unit_rate": unit.get("usd_rate"),
                    "freight": freight.get("minor"),
                    "freight_currency": freight.get("currency"),
                    "freight_rate": freight.get("usd_rate"),
                    "duty": values["duty_bps"],
                    "quantity": values["quantity"],
                    "ddp": values["ddp"],
                    "customs": values["customs_fee_minor"],
                    "payment_bps": values["payment_fee_bps"],
                    "payment_fixed": values["payment_fee_fixed_minor"],
                    "shopify_bps": values["shopify_fee_bps"],
                    "returns_bps": values["returns_bps"],
                    "ad_cost": values["ad_cost_minor"],
                    "freight_gap": values["freight_gap"],
                },
            ).mappings()
            got = result(row.one())
            if got != result(vector["expected"]):
                wrong[vector["name"]] = got
    assert wrong == {}


def observe[T: Base](
    session: Session, model: type[T], source_id: int, at: datetime, **values: Any
) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id,
        run_id=run.id,
        captured_at=at,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=at, raw_payload_id=payload.id, observed_for=at.date(), **values)
    session.add(row)
    session.flush()
    return row


def rate(session: Session, currency: str, usd_rate: str | None, at: datetime) -> None:
    if currency != "USD" and usd_rate is not None:
        observe(
            session, FxRate, FX, at, date=at.date(), base="USD", quote=currency, source="blend",
            rate=Decimal(usd_rate),
        )  # fmt: skip


def seed(session: Session, vector: dict[str, Any]) -> tuple[UUID, UUID, Provenance | None]:
    """The vector as collected rows: a store price, a supplier listing, its cost, its US quote."""
    values = vector["inputs"]
    workspace = Workspace(name=vector["name"][:80])
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceSettings(
            workspace_id=workspace.id,
            **{column: values[name] for name, column in SETTINGS.items()},
        )
    )
    product = Product(name="Sunset lamp")
    session.add(product)
    session.flush()
    price = None
    if values["price_minor"] is not None:
        store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
        session.add(store)
        session.flush()
        listing = Listing(
            source_id=SHOPIFY, external_id=uuid4().hex, url="https://store.example.test/p",
            title="Sunset lamp", product_id=product.id, store_id=store.id,
        )  # fmt: skip
        session.add(listing)
        session.flush()
        snap = observe(
            session, ListingSnapshot, SHOPIFY, PRICED, listing_id=listing.id, values_hash="h",
            currency="USD", price_min_minor=values["price_minor"],
        )  # fmt: skip
        price = Provenance("shopify_stores", PRICED, snap.raw_payload_id)
    unit, freight, gap = values["unit_cost"], values["freight"], values["freight_gap"]
    if unit is None and freight is None and gap == "freight_missing":
        return workspace.id, product.id, price  # no supplier listing at all
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add(supplier)
    session.flush()
    for earlier in vector.get("earlier_listings", []):  # created first, so the lower ids
        rival = Listing(
            source_id=CJ, external_id=uuid4().hex, url="https://cj.example.test/q",
            title="Sunset lamp", product_id=product.id, supplier_id=supplier.id,
        )  # fmt: skip
        session.add(rival)
        session.flush()
        observe(
            session, ListingSnapshot, CJ, COSTED, listing_id=rival.id, values_hash="h",
            currency="USD", price_min_minor=earlier["unit_minor"],
        )  # fmt: skip
        observe(
            session, ShippingOption, CJ, PRICED, listing_id=rival.id, origin_country="CN",
            destination_country="US", quantity=1, method="CJPacket",
            cost_minor=earlier["freight_minor"], currency="USD",
        )  # fmt: skip
    listing = Listing(
        source_id=CJ, external_id=uuid4().hex, url="https://cj.example.test/p",
        title="Sunset lamp", product_id=product.id, supplier_id=supplier.id,
    )  # fmt: skip
    session.add(listing)
    session.flush()
    if unit is None:  # an older priced snapshot: the latest one has no price, and no fallback
        observe(
            session, ListingSnapshot, CJ, COSTED - timedelta(days=1), listing_id=listing.id,
            values_hash="h", currency="USD", price_min_minor=1,
        )  # fmt: skip
    observe(
        session, ListingSnapshot, CJ, COSTED, listing_id=listing.id, values_hash="h",
        currency=(unit or {}).get("currency", "USD"), price_min_minor=(unit or {}).get("minor"),
    )  # fmt: skip
    if unit is not None:
        rate(session, unit["currency"], unit["usd_rate"], COSTED)
    variant = None
    if gap == "freight_variant_mismatch":  # two live variants; the quote names one of them
        for external_id in ("a", "b"):
            session.add(ListingVariant(listing_id=listing.id, external_id=external_id))
        session.flush()
        variant = session.scalars(
            select(ListingVariant.id).where(ListingVariant.listing_id == listing.id)
        ).first()
    if freight is not None or variant is not None:
        freight = freight or {"minor": 485, "currency": "USD", "usd_rate": None}
        observe(
            session, ShippingOption, CJ, PRICED, listing_id=listing.id, variant_id=variant,
            origin_country="CN", destination_country="US", quantity=1, method="CJPacket",
            cost_minor=freight["minor"], currency=freight["currency"],
        )  # fmt: skip
        rate(session, freight["currency"], freight["usd_rate"], PRICED)
    return workspace.id, product.id, price


def economics(session: Session, workspace_id: UUID, product_id: UUID) -> Any:
    view = workspace_product_economics.c
    return (
        session.execute(
            select(workspace_product_economics).where(
                view.workspace_id == workspace_id, view.product_id == product_id
            )
        )
        .mappings()
        .one()
    )


def parsed(sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The view's jsonb `sources` as Provenance fields: `as_of` back to a datetime."""
    return {
        name: {**trace, "as_of": trace["as_of"] and datetime.fromisoformat(trace["as_of"])}
        for name, trace in sources.items()
    }


@pytest.mark.db
def test_the_view_matches_every_golden_vector_and_the_loader(db_engine: Engine) -> None:
    """Each `view: true` vector, seeded as rows, reads the same from the view as from the
    vector and from calculate(): lines, totals, complete, missing, supplier, method, sources."""
    wrong = {}
    with Session(db_engine) as session:
        for vector in (vector for vector in VECTORS if vector["view"]):
            savepoint = session.begin_nested()  # FX rates are global: one vector at a time
            workspace_id, product_id, price = seed(session, vector)
            settings = session.get_one(WorkspaceSettings, workspace_id)
            reference = None if price is None else (vector["inputs"]["price_minor"], price)
            calc = calculate(session, settings, product_id, reference_price=reference)
            row = economics(session, workspace_id, product_id)
            sources = parsed(row["sources"])
            observed = (trace.as_of for trace in calc.sources.values())
            checks = {
                "vector": result(row) == result(vector["expected"]),
                "loader": result(row) == result(asdict(calc.cost)),
                "supplier": (row["supplier_listing_id"], row["method"])
                == (calc.listing_id, calc.method),
                "sources": sources == {name: asdict(trace) for name, trace in calc.sources.items()},
                "as_of": row["as_of"] == min(filter(None, observed), default=None),
                # An owner estimate reaches the view as a Settings value, with its source.
                "estimates": all(
                    sources[name]["source"] == "settings" for name in vector["inputs"]["estimates"]
                ),
            }
            if not all(checks.values()):
                wrong[vector["name"]] = {
                    "failed": [name for name, ok in checks.items() if not ok],
                    "view": result(row) | {"sources": sources},
                    "loader": result(asdict(calc.cost)) | {"sources": calc.sources},
                }
            savepoint.rollback()
    assert wrong == {}
    assert sum(vector["view"] for vector in VECTORS) == 28


@pytest.mark.db
def test_a_workspace_reads_only_its_own_settings(db_engine: Engine) -> None:
    vector = VECTORS[0]  # the worked example: 1503 at 2.9% + $0.30 in workspace A
    with Session(db_engine) as session:
        a, product_id, _ = seed(session, vector)
        b = Workspace(name="B")
        session.add(b)
        session.flush()
        session.add(WorkspaceSettings(workspace_id=b.id, duty_default_bps=2000))
        session.flush()
        assert economics(session, a, product_id)["margin_minor"] == 1503
        assert economics(session, b.id, product_id)["margin_minor"] == 1503 + 117 + 150
        assert economics(session, b.id, product_id)["sources"]["duty_bps"]["source"] == "settings"
        survivor = Product(name="Survivor")
        session.add(survivor)
        session.flush()
        session.get_one(Product, product_id).merged_into_id = survivor.id  # merged: no answer
        session.flush()
        view = workspace_product_economics.c
        assert session.scalar(select(view.product_id).where(view.product_id == product_id)) is None


@pytest.mark.db
def test_the_view_and_the_loader_both_put_in_stock_listings_first(db_engine: Engine) -> None:
    """DEC-291: a better margin known out of stock loses in both, until nothing is in stock."""
    vector = VECTORS[0]  # the worked example: listing `kept`, margin 1503
    with Session(db_engine) as session:
        workspace_id, product_id, price = seed(session, vector)
        assert price is not None
        settings = session.get_one(WorkspaceSettings, workspace_id)
        reference = (vector["inputs"]["price_minor"], price)
        kept = session.scalars(
            select(Listing.id).where(
                Listing.product_id == product_id, Listing.supplier_id.is_not(None)
            )
        ).one()
        supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
        session.add(supplier)
        session.flush()
        gone = Listing(
            source_id=CJ, external_id=uuid4().hex, url="https://cj.example.test/q",
            title="Sunset lamp", product_id=product_id, supplier_id=supplier.id,
        )  # fmt: skip
        session.add(gone)
        session.flush()
        observe(
            session, ListingSnapshot, CJ, COSTED, listing_id=gone.id, values_hash="h",
            currency="USD", price_min_minor=500, stock=0,
        )  # fmt: skip
        observe(
            session, ShippingOption, CJ, PRICED, listing_id=gone.id, origin_country="CN",
            destination_country="US", quantity=1, method="CJPacket", cost_minor=300,
            currency="USD",
        )  # fmt: skip

        def pick() -> int | None:
            """The loader's and the view's default answer, held equal; the listing they cost."""
            calc = calculate(session, settings, product_id, reference_price=reference)
            row = economics(session, workspace_id, product_id)
            assert result(row) == result(asdict(calc.cost))
            assert (row["supplier_listing_id"], row["method"]) == (calc.listing_id, calc.method)
            assert parsed(row["sources"]) == {
                name: asdict(trace) for name, trace in calc.sources.items()
            }
            return calc.listing_id

        assert pick() == kept
        sold_out = calculate(
            session, settings, product_id, reference_price=reference, listing_id=gone.id
        )
        assert sold_out.cost.margin_minor == 2999 - 900 - 117 - 150  # better than kept's 1503
        observe(
            session, ListingSnapshot, CJ, COSTED, listing_id=kept, values_hash="h",
            currency="USD", price_min_minor=620, available=False,
        )  # fmt: skip  # a later row of the same capture: now nothing is in stock
        assert pick() == gone.id


def stock_capture(session: Session, listing_id: int, at: datetime, stock: int | None) -> None:
    """A CJ stock capture's listing row: stock and no price (DEC-348)."""
    row = observe(
        session, ListingSnapshot, CJ, at, listing_id=listing_id, values_hash="s", currency="USD",
        stock=stock,
    )  # fmt: skip
    session.get_one(RawPayload, row.raw_payload_id).request = {"endpoint": STOCK_ENDPOINT}
    session.flush()


@pytest.mark.db
def test_a_cj_stock_row_is_read_for_stock_and_never_for_price(db_engine: Engine) -> None:
    """DEC-348, in the loader and the view alike: a newest stock-only row keeps the listing's
    cost, a later price-only row doesn't hide its stock-out, and an unknown total supersedes it."""
    vector = VECTORS[0]  # listing `kept`, margin 1503
    with Session(db_engine) as session:
        workspace_id, product_id, price = seed(session, vector)
        assert price is not None
        settings = session.get_one(WorkspaceSettings, workspace_id)
        reference = (vector["inputs"]["price_minor"], price)
        kept = session.scalars(
            select(Listing).where(
                Listing.product_id == product_id, Listing.supplier_id.is_not(None)
            )
        ).one()
        gone = Listing(
            source_id=CJ, external_id=uuid4().hex, url="https://cj.example.test/q",
            title="Sunset lamp", product_id=product_id, supplier_id=kept.supplier_id,
        )  # fmt: skip
        session.add(gone)
        session.flush()
        priced = observe(
            session, ListingSnapshot, CJ, COSTED, listing_id=gone.id, values_hash="h",
            currency="USD", price_min_minor=500,
        )  # fmt: skip
        observe(
            session, ShippingOption, CJ, PRICED, listing_id=gone.id, origin_country="CN",
            destination_country="US", quantity=1, method="CJPacket", cost_minor=300,
            currency="USD",
        )  # fmt: skip

        def pick() -> int | None:
            """The loader's and the view's default answer, held equal; the listing they cost."""
            calc = calculate(session, settings, product_id, reference_price=reference)
            row = economics(session, workspace_id, product_id)
            assert result(row) == result(asdict(calc.cost))
            assert row["supplier_listing_id"] == calc.listing_id
            assert parsed(row["sources"]) == {
                name: asdict(trace) for name, trace in calc.sources.items()
            }
            return calc.listing_id

        assert pick() == gone.id  # in stock, and the better margin (1832)
        stock_capture(session, gone.id, COSTED + timedelta(hours=1), 0)  # sold out: newest row
        assert pick() == kept.id
        cost = unit_cost(session, gone.id, None)
        assert cost is not None and cost.raw_payload_id == priced.raw_payload_id
        observe(
            session, ListingSnapshot, CJ, COSTED + timedelta(hours=2), listing_id=gone.id,
            values_hash="h", currency="USD", price_min_minor=500,
        )  # fmt: skip  # a later price row, stock null: the stock-out is still current
        assert not stocked(session, gone.id) and pick() == kept.id
        stock_capture(session, gone.id, COSTED + timedelta(hours=3), None)
        assert stocked(session, gone.id)  # an unknown total supersedes the stock-out
        assert pick() == gone.id  # costed from its price row, under a newer stock row
