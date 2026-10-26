"""Workspace product economics: CJ stock rows are read for stock, never for price (DEC-348).

The view is 0023's with two edits, as `unit_cost()` and `stocked()` now read. A CJ stock capture
appends a listing row that carries stock and no price. The unit-cost lateral skips those rows, so
a stock change never hides the listing's cost. The in-stock-first lateral takes the newest row
with stock fields or from a stock capture, so a later price row never hides a stock-out.

Frozen schema: do not import live application models into a revision.
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None

STOCK_CAPTURE = "payload.request->>'endpoint' = '/product/stock/getInventoryByPid'"
EDITS = (
    (
        "    LEFT JOIN LATERAL (  -- the latest supplier snapshot, if it has a price:"
        " never an older one\n",
        "    LEFT JOIN LATERAL (  -- the latest supplier snapshot, if it has a price: never an"
        " older one;\n    -- a CJ stock capture's row carries no price and is skipped (DEC-348)\n",
    ),
    (
        "            WHERE snap.listing_id = l.id\n",
        "            WHERE snap.listing_id = l.id\n"
        "              AND payload.request->>'endpoint' IS DISTINCT FROM\n"
        "                  '/product/stock/getInventoryByPid'\n",
    ),
    (
        "    LEFT JOIN LATERAL (  -- the latest snapshot, priced or not: is the listing known out"
        " of stock?\n"
        "        SELECT snap.available IS FALSE OR snap.stock <= 0 AS sold_out\n"
        "        FROM listing_snapshots snap\n"
        "        WHERE snap.listing_id = l.id\n",
        "    LEFT JOIN LATERAL (  -- the newest stock reading: is the listing known out of stock?\n"
        "        -- A row with stock fields, or a CJ stock capture's: an unknown total supersedes\n"
        "        SELECT snap.available IS FALSE OR snap.stock <= 0 AS sold_out\n"
        "        FROM listing_snapshots snap\n"
        "        JOIN raw_payloads payload ON payload.id = snap.raw_payload_id\n"
        "        WHERE snap.listing_id = l.id\n"
        "          AND (snap.available IS NOT NULL OR snap.stock IS NOT NULL\n"
        f"               OR {STOCK_CAPTURE})\n",
    ),
)


def previous_view() -> str:
    """0023's frozen view text, built by that revision's file."""
    path = Path(__file__).with_name("0023_economics_cheapest_fallback.py")
    spec = importlib.util.spec_from_file_location("revision_0023", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.cheapest_fallback())


def listing_stock() -> str:
    view = previous_view()
    for old, new in EDITS:
        assert view.count(old) == 1, old
        view = view.replace(old, new)
    return view


def upgrade() -> None:
    op.execute(listing_stock())


def downgrade() -> None:
    # 0023's view reads a CJ stock row as the latest price (none) and hides it from stock reads.
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM listing_snapshots snap
                JOIN raw_payloads payload ON payload.id = snap.raw_payload_id
                WHERE {STOCK_CAPTURE}
            ) THEN
                RAISE EXCEPTION 'CJ stock rows 0023 misreads exist; refusing a lossy downgrade';
            END IF;
        END
        $$
    """)
    op.execute(previous_view())
