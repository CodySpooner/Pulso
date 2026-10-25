"""Workspace product economics: the default supplier pick puts in-stock listings first (DEC-291).

The view is 0010's with two edits, as `calculate()` now picks: each listing's latest snapshot
says whether it is known to be out of stock (DEC-243: `available` false, or stock 0), and the
pick ranks every other listing first. With none in stock, the best out-of-stock one still costs.

Frozen schema: do not import live application models into a revision.
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

STOCK = """    LEFT JOIN LATERAL usd_rate(unit.currency, unit.captured_at) unit_fx ON true
    LEFT JOIN LATERAL (  -- the latest snapshot, priced or not: is the listing known out of stock?
        SELECT snap.available IS FALSE OR snap.stock <= 0 AS sold_out
        FROM listing_snapshots snap
        WHERE snap.listing_id = l.id
        ORDER BY snap.captured_at DESC, snap.id DESC
        LIMIT 1
    ) stock ON true
"""
EDITS = (
    ("    LEFT JOIN LATERAL usd_rate(unit.currency, unit.captured_at) unit_fx ON true\n", STOCK),
    (  # no snapshot, or one without stock fields, is not known out of stock (NULL sorts as false)
        "    ORDER BY l.id IS NULL, cost.complete DESC,",
        "    ORDER BY l.id IS NULL, stock.sold_out IS TRUE, cost.complete DESC,",
    ),
)


def previous_view() -> str:
    """0010's frozen view text, read from that revision's file."""
    path = Path(__file__).with_name("0010_workspace_product_economics.py")
    spec = importlib.util.spec_from_file_location("revision_0010", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.VIEW).replace("CREATE VIEW", "CREATE OR REPLACE VIEW")


def in_stock_first() -> str:
    view = previous_view()
    for old, new in EDITS:
        assert view.count(old) == 1, old
        view = view.replace(old, new)
    return view


def upgrade() -> None:
    op.execute(in_stock_first())


def downgrade() -> None:
    op.execute(previous_view())
