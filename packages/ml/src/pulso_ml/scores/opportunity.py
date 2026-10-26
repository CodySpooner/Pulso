"""Opportunity v0 (SPEC §7, vault Intelligence/Opportunity Score, DEC-331).

Workspace-scoped: margin depends on the workspace's fees, so it is computed at read time from
the stored scores and the workspace_product_economics view, and never written to `scores`
(DEC-041).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.orm import Session

from pulso_core.landed_cost import Amount, Inputs, landed_cost
from pulso_core.models import Score, WorkspaceSettings
from pulso_core.scores import Component, Explanation, Kind, Penalty, explain, latest, version
from pulso_ml.features.daily import cutoff

VIEW = "workspace_product_economics"  # the margin component's source


@dataclass(frozen=True)
class Config:
    revision: int = 1  # bump with any change to the rules below; 1: stale rows (DEC-354)
    # Weights are judgement calls until Phase 6 data exists.
    momentum: float = 0.40  # weight of Trend Score v0 (Beta) until a published forecast exists
    margin: float = 0.30  # weight of the contribution margin before ads, against the floor
    room: float = 0.20  # weight of 100 − Saturation
    safety: float = 0.10  # weight of 100 − Risk: no source until Phase 5, always missing
    floor_bps: int = 3000  # m_ref, contribution margin before ads (a guess): Margin 50 at it
    floor_cap: float = 25.0  # the most Opportunity can be while the margin is under the floor
    duty_not_set: float = 0.2  # confidence taken off while the margin has no duty line


CONFIG = Config()
VERSION, _ = version(CONFIG)  # `{revision:03d}-{hash12}` (DEC-306 d)


class Stored(NamedTuple):
    """A stored Trend or Saturation row as Opportunity reads it."""

    value: float | None  # 0–100; None: a NULL row (insufficient signal)
    as_of: datetime  # its inputs were captured before this


class Margin(NamedTuple):
    """The workspace's economics row as Opportunity reads it."""

    bps: int | None  # contribution before ads / price; None: the row is incomplete
    duty_not_set: bool  # bps is landed_cost() at duty 0, since the workspace set no duty
    as_of: datetime | None  # the oldest input it uses


class Opportunity(NamedTuple):
    value: float | None  # 0–100 to 0.1; None: no input present
    as_of: datetime | None  # the oldest present input
    explanation: Explanation


def stored(row: Score | None) -> Stored | None:
    """A `scores` row: as of its day's cutoff, or its computation when that came first."""
    if row is None:
        return None
    value = None if row.value is None else float(row.value)
    return Stored(value, min(cutoff(row.date), row.computed_at))


def latest_rows(
    session: Session, kind: Kind, products: Sequence[UUID] | Select[tuple[UUID]]
) -> dict[UUID, Score]:
    """Each product's newest `kind` row, in one query for any number of products (imp-488):
    `pulso_core.scores.latest` over a list of ids or a query of them."""
    query = latest(kind).where(Score.product_id.in_(products))
    return {row.product_id: row for row in session.scalars(query)}


def margin_of(row: Mapping[Any, Any] | None, settings: WorkspaceSettings | None) -> Margin | None:
    """The economics row's margin; with duty the only gap, landed_cost() of its USD lines at duty
    0, so the one landed-cost function prices both (DEC-246). None: no settings row yet."""
    if row is None or settings is None:
        return None
    missing: Sequence[str] = row["missing"]
    if row["complete"] or list(missing) != ["duty_not_set"]:
        return Margin(row["margin_bps"], False, row["as_of"])
    undutied = landed_cost(
        Inputs(
            price_minor=row["price_minor"],
            unit_cost=Amount(row["goods_minor"], "USD"),  # quantity 1, already in USD cents
            freight=Amount(row["freight_minor"], "USD"),
            duty_bps=0,
            customs_fee_minor=row["customs_fee_minor"],
            payment_fee_bps=settings.payment_fee_bps,
            payment_fee_fixed_minor=settings.payment_fee_fixed_minor,
            shopify_fee_bps=settings.shopify_fee_bps,
            returns_bps=settings.returns_bps,
        )
    )
    return Margin(undutied.margin_bps, True, row["as_of"])


def opportunity(
    trend: Stored | None, saturation: Stored | None, margin: Margin | None, now: datetime
) -> Opportunity:
    """ "Should I test this?" for one workspace, 0–100: higher is a better test.

    Each input is a 0–100 value (the explanation's `z`, so its `contribution` is its points):
    - trend (momentum): the latest Trend Score v0, marked Beta, until a published 14-day
      forecast exists; then 100 × p14 (Phase 6).
    - margin: clamp(100 × m / (2 × m_ref), 0, 100), m the contribution margin before ads from
      the workspace's landed cost and m_ref `floor_bps`: 50 at the floor, 100 at twice it.
    - saturation (room): 100 − the latest Saturation.
    - risk (safety): 100 − Risk, no source until Phase 5, so always missing.

    O = Σ w × value / Σ w over the present inputs: a missing one gets weight 0 and the rest
    renormalise (DEC-040). A NULL stored row is missing with its score as source ("insufficient
    signal"); no row, or no workspace settings, is missing with none ("no source yet").

    - Margin floor: with m under m_ref, Opportunity = min(O, `floor_cap`); the cut is the
      `margin_floor` penalty and the reason reads "margin below your floor".
    - Freshness at `now`, the read (DEC-354): a Trend or Saturation row over 1.5 days old counts
      half in confidence; over 3 days it is stale, so missing. Either lists `stale_input`.
    - Duty not set: m is costed at duty 0, never withheld; confidence loses `duty_not_set` and
      the explanation lists the caution.

    Opportunity = round(O, 1), as of its oldest present input; no value when none is present.
    """

    def part(
        name: str,
        role: str,
        weight: float,
        source: str | None,
        read: tuple[float, float, datetime | None] | None,
    ) -> Component:
        """`read` is (raw, 0–100 value, as_of); None: missing, "no source yet" with no source."""
        if read is None:
            return Component(name=name, family=role, source=source, weight=weight, missing=True)
        raw, z, as_of = read
        return Component(
            name=name, family=role, source=source, weight=weight, raw=raw, z=z, as_of=as_of
        )

    t = None if trend is None else trend.value
    s = None if saturation is None else saturation.value
    m = None if margin is None else margin.bps
    components = [
        part(
            "trend",
            "momentum",
            CONFIG.momentum,
            None if trend is None else "trend",
            None if trend is None or t is None else (t, t, trend.as_of),
        ),
        part(
            "margin",
            "margin",
            CONFIG.margin,
            None if margin is None else VIEW,
            None
            if margin is None or m is None
            else (m / 10_000, min(100.0, max(0.0, 100 * m / (2 * CONFIG.floor_bps))), margin.as_of),
        ),
        part(
            "saturation",
            "room",
            CONFIG.room,
            None if saturation is None else "saturation",
            None if saturation is None or s is None else (s, 100 - s, saturation.as_of),
        ),
        part("risk", "safety", CONFIG.safety, None, None),
    ]
    total, explanation = explain(CONFIG, components, as_of=now)
    unset = m is not None and margin is not None and margin.duty_not_set
    cautions = (*explanation.cautions, *(("duty_not_set",) if unset else ()))
    confidence = max(0.0, (explanation.confidence or 0.0) - CONFIG.duty_not_set * unset)
    update: dict[str, Any] = {"confidence": round(confidence, 4), "cautions": cautions}
    if total is None:
        update["reason"] = "no trend, margin or saturation yet"
    elif m is not None and m < CONFIG.floor_bps:
        capped = min(total, CONFIG.floor_cap)
        update["penalties"] = (
            Penalty(name="margin_floor", source=VIEW, raw=m / 10_000, points=total - capped),
        )
        update["reason"] = "margin below your floor"
        total = capped
    present = [c.as_of for c in explanation.components if not c.missing and c.as_of]
    return Opportunity(
        None if total is None else round(total, 1),
        min(present, default=None),
        Explanation(**{**dict(explanation), **update}),  # validated, as Trend's penalties are
    )
