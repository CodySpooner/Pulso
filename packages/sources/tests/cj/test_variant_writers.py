"""P1-37 probe C1 (DEC-120): CJ detail and stock variant rows are change-only per writer."""

import json
from dataclasses import replace
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import ListingVariant, VariantSnapshot
from pulso_sources.cj import collect
from pulso_sources.cj.tracked import VARIANT_WRITERS, TrackedAdapter, plan
from pulso_sources.framework import Target, current_fields, enqueue_run

from .test_cj import fixture
from .test_persistence import settings


def tracked_run(session: Session, stock: bytes | None = None) -> None:
    bodies = {
        "/product/query": fixture("detail"),
        "/product/stock/getInventoryByPid": stock or fixture("stock"),
    }
    targets = [
        Target(
            t.scope,
            t.target_id,
            [
                replace(r, mode="fixture", body=bodies[str(r.params["endpoint"])])
                for r in t.requests
            ],
        )
        for t in plan(["fixture-product"])
    ]
    queued = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    run = collect(session, queued.id, targets, settings=settings(), adapter=TrackedAdapter())
    assert run.status == "success", (run.error_code, run.error_message)


def rows(session: Session, vid: str) -> tuple[dict[str, int], list[VariantSnapshot]]:
    variant = session.scalars(select(ListingVariant).filter_by(external_id=vid)).one()
    query = select(VariantSnapshot).filter_by(variant_id=variant.id).order_by(VariantSnapshot.id)
    return {"variant_id": variant.id}, list(session.scalars(query))


def test_alternating_detail_and_stock_keep_their_own_current_fields(session: Session) -> None:
    tracked_run(session)
    tracked_run(session)  # the next day: identical detail and stock bodies
    key, (detail_row, stock_row) = rows(session, "fixture-variant-a")
    current = current_fields(session, VariantSnapshot, key=key, writers=VARIANT_WRITERS)
    assert {name: row.id for name, row in current.items()} == {
        "price_minor": detail_row.id,
        "inventory_quantity": stock_row.id,
    }
    assert (detail_row.price_minor, stock_row.inventory_quantity) == (125, 15)
    assert detail_row.raw_payload_id != stock_row.raw_payload_id

    key_b, (_, empty_stock) = rows(session, "fixture-variant-b")
    current_b = current_fields(session, VariantSnapshot, key=key_b, writers=VARIANT_WRITERS)
    assert current_b["inventory_quantity"].id == empty_stock.id  # explicit unknown, not missing
    assert empty_stock.inventory_quantity is None

    changed = json.loads(fixture("stock"))
    changed["data"]["variantInventories"][0]["inventory"][0]["totalInventory"] = 13
    tracked_run(session, json.dumps(changed).encode())
    _, history = rows(session, "fixture-variant-a")
    assert len(history) == 3 and history[-1].inventory_quantity == 16
    cutoff = history[-1].captured_at.replace(tzinfo=UTC)
    as_of = current_fields(
        session, VariantSnapshot, key=key, writers=VARIANT_WRITERS, captured_before=cutoff
    )
    assert {name: row.id for name, row in as_of.items()} == {
        "price_minor": detail_row.id,
        "inventory_quantity": stock_row.id,
    }
