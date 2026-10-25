"""Workspace product economics: with nothing complete, the lowest goods + freight costs (DEC-341).

The view is 0014's with one edit, as `calculate()` now picks: among incomplete listings with the
fewest missing inputs, the lowest goods + freight comes before the lowest id. While duty is not
set, every listing is incomplete, and price, fees, returns and the customs fee are the same for
each, so that is the best margin at duty 0, the one Opportunity scores (XR-66, DEC-331 b).

Frozen schema: do not import live application models into a revision.
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "0023"
down_revision = "0021"
branch_labels = None
depends_on = None

EDITS = (
    (
        "    -- best(): the highest complete margin; with none, the fewest missing;"
        " then the lowest id\n",
        "    -- best(): the highest complete margin; with none, the fewest missing, the lowest\n"
        "    -- goods + freight (duty unset: the best margin at duty 0), then the lowest id\n",
    ),
    (  # numeric: goods + freight can pass BIGINT where each line fits
        "             cardinality(cost.missing), l.id\n",
        "             cardinality(cost.missing),"
        " cost.goods_minor::numeric + cost.freight_minor NULLS LAST, l.id\n",
    ),
)


def previous_view() -> str:
    """0014's frozen view text, built by that revision's file."""
    path = Path(__file__).with_name("0014_economics_in_stock_first.py")
    spec = importlib.util.spec_from_file_location("revision_0014", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return str(module.in_stock_first())


def cheapest_fallback() -> str:
    view = previous_view()
    for old, new in EDITS:
        assert view.count(old) == 1, old
        view = view.replace(old, new)
    return view


def upgrade() -> None:
    op.execute(cheapest_fallback())


def downgrade() -> None:
    op.execute(previous_view())
