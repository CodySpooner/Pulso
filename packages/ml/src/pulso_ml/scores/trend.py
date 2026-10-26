"""Trend Score v0 (SPEC §7, vault Intelligence/Trend Score, DEC-323): pure, no tables.

Reads one day's product_daily_features rows (DEC-275, DEC-311 b) and the rows a week before for
acceleration; SC-6 stores the result.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NamedTuple, Protocol
from uuid import UUID

from pulso_core.scores import Component, Explanation, Penalty, explain, version
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.features.repository import FAMILIES
from pulso_ml.scores import robust_z


@dataclass(frozen=True)
class Config:
    revision: int = 1  # bump with any change to the rules below; 1: stale is missing (DEC-354)
    feature_version: str = FEATURE_VERSION  # the rows these rules read
    # Weights and the penalty cap are judgement calls until Phase 6 data exists.
    g7: float = 0.40  # weight of velocity growth in the primary demand family; required
    acc: float = 0.20  # weight of acceleration in the same family
    gt_slope: float = 0.25  # weight of the search-interest slope (R-18)
    ads_growth: float = 0.15  # weight of ad-count growth: no source yet, always missing
    penalty: float = 15.0  # points off at Saturation 100; none at or below 50
    min_n: int = 30  # a category needs this many products with the input, or its parent is used
    cap: float = 3.0  # robust z is winsorized to ±cap


CONFIG = Config()
VERSION, _ = version(CONFIG)  # `{revision:03d}-{hash12}` (DEC-306 d)


class Row(Protocol):
    """A product_daily_features row: a `Feature` or its model."""

    @property
    def product_id(self) -> UUID: ...
    @property
    def family(self) -> str: ...
    @property
    def growth_7d(self) -> float | None: ...
    @property
    def has_gap(self) -> bool: ...
    @property
    def features(self) -> dict[str, Any] | None: ...


class Trend(NamedTuple):
    value: float | None  # 0–100, higher is a stronger trend; None: insufficient signal
    explanation: Explanation | None
    reason: str | None = None  # why there is no value


def trend_scores(
    rows: Iterable[Row],
    week_ago: Iterable[Row],
    categories: Mapping[UUID, Sequence[int]],
    primary: Mapping[UUID, str],
    saturation: Mapping[UUID, float | None],
    as_of: datetime,
) -> dict[UUID, Trend]:
    """How strongly each product is trending on day t, 0–100 (Beta until a forecast is promoted).

    `categories` holds every product to score: its category and that category's ancestors,
    nearest first (empty when it has none). `rows` are day t's feature rows, every family;
    `week_ago` are day t−7's. `primary` names each product's primary demand family (vault
    Demand Signals rule 1); `saturation` holds its Saturation Score (SC-3). `as_of` is day t's
    cutoff: inputs were captured before it (DEC-031), and a feature-row input with no capture time
    of its own is as of it. Each input is a
    robust z within the product's category, falling back up its ancestors to every product when
    n < 30 or MAD = 0, winsorized to ±3 (Score Definitions §4):
    - <family>_g7: G7 = ln((V7(t) + 5) / (V7(t−7) + 5)) in the primary family, as stored: log
      growth, so 3 → 30 units reads 1.48, never +900%, and both weeks count only the listings
      covered at t−14 and t, so newly tracked listings never read as growth. Required.
    - <family>_acc: G7(t) − G7(t−7) in the same family, from the two days' rows.
    - gt_slope: ln((m4 + 1) / (m8 + 1)) within one Trends capture, as stored (R-18).
    - ads_growth: no source yet, so always missing.

    Each input's cohort is every product asked for with a value in it; families never mix.
    Freshness is taken at `as_of` (DEC-354): a search slope captured over 3 weeks before it is
    stale, so missing. T = Σ w × z / Σ w over the present inputs: a missing one gets weight 0 and
    the rest renormalise (DEC-040). Then pre = 50 + 50 × T / 3, and
    Trend = clamp(pre − penalty, 0, 100) with penalty = 15 × max(0, (Saturation − 50) / 50)
    points. Without a Saturation the penalty is missing: nothing is taken off and `missing` names
    it.

    No value, with its reason, never 0:
    - no demand family: the product has no primary family. Search slope alone never scores.
    - no velocity growth: no G7 in that family on day t (no row, or a NULL one).
    - velocity growth doesn't vary: no category, nor the whole set, has a spread to normalise by.
    """
    now = {(r.product_id, r.family): r for r in rows if r.product_id in categories}
    before = {(r.product_id, r.family): r for r in week_ago}
    raws: defaultdict[str, dict[UUID, float]] = defaultdict(dict)
    for (p, fam), row in now.items():
        if fam == "gt_interest":
            if (slope := (row.features or {}).get("gt_slope")) is not None:
                raws["gt_slope"][p] = slope
        elif (g7 := row.growth_7d) is not None:
            raws[f"{fam}_g7"][p] = g7
            prev = before.get((p, fam))
            if prev is not None and prev.growth_7d is not None:
                raws[f"{fam}_acc"][p] = g7 - prev.growth_7d
    zs = {k: robust_z(v, categories, min_n=CONFIG.min_n, cap=CONFIG.cap) for k, v in raws.items()}

    def component(
        name: str,
        family: str,
        source: str,
        weight: float,
        product: UUID,
        gap: bool,
        captured: datetime | None = None,
    ) -> Component:
        found = zs.get(name, {}).get(product)
        return Component(
            name=name,
            family=family,
            source=source,
            weight=weight,
            raw=raws.get(name, {}).get(product),
            z=found[0] if found else None,
            normalization=found[1] if found else None,
            as_of=captured or (as_of if found else None),
            missing=found is None,
            gap=gap,
        )

    scores = {}
    for product in categories:
        family = primary.get(product)
        if family is None:
            scores[product] = Trend(None, None, "no demand family")
            continue
        if product not in raws.get(f"{family}_g7", {}):
            scores[product] = Trend(None, None, "no velocity growth")
            continue
        if product not in zs[f"{family}_g7"]:
            scores[product] = Trend(None, None, "velocity growth doesn't vary")
            continue
        source, row = FAMILIES[family].source, now[product, family]
        prev, search = before.get((product, family)), now.get((product, "gt_interest"))
        captured = search.features.get("gt_as_of") if search and search.features else None
        components = [
            component(f"{family}_g7", family, source, CONFIG.g7, product, row.has_gap),
            component(
                f"{family}_acc",
                family,
                source,
                CONFIG.acc,
                product,
                row.has_gap or (prev is not None and prev.has_gap),
            ),
            component(
                "gt_slope",
                "gt_interest",
                "google_trends",
                CONFIG.gt_slope,
                product,
                False,  # a slope reads every day of 12 complete weeks in one capture
                datetime.fromisoformat(captured) if captured else None,
            ),
            Component(
                name="ads_growth", family="ads", source=None, weight=CONFIG.ads_growth, missing=True
            ),
        ]
        total, explanation = explain(CONFIG, components, as_of=as_of)
        assert total is not None  # G7 is present
        crowded = saturation.get(product)
        penalty = Penalty(
            name="saturation",
            source="shopify_stores",
            raw=crowded,
            points=None if crowded is None else CONFIG.penalty * max(0.0, (crowded - 50) / 50),
            missing=crowded is None,
        )
        value = min(100.0, max(0.0, 50 + 50 * total / 3 - (penalty.points or 0.0)))
        missing = (*explanation.missing, *(["saturation"] if penalty.missing else []))
        scores[product] = Trend(
            value, Explanation(**{**dict(explanation), "penalties": (penalty,), "missing": missing})
        )
    return scores
