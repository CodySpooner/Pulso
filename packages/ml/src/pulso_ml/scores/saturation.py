"""Saturation Score v0 (SPEC §7, vault Intelligence/Saturation Score, DEC-318): pure, no tables.

Reads one day's `shp_sellers` rows of product_daily_features (DEC-311 c); SC-6 stores the result.
"""

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, NamedTuple, Protocol
from uuid import UUID

from pulso_core.scores import Component, Explanation, explain, version
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.scores import robust_z

Band = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class Config:
    revision: int = 0  # bump with any change to the rules below
    feature_version: str = FEATURE_VERSION  # the shp_sellers rows these rules read
    # Weights are judgement calls until Phase 6 data exists; CJ listings wait for Demand Signals.
    shp_sellers: float = 0.40  # weight of ln(1 + stores selling it), every tracked store
    shp_seller_g28: float = 0.25  # weight of seller growth over the stable panel
    ads_active: float = 0.25  # weight of active advertisers: no source yet, always missing
    min_n: int = 30  # a category needs this many products with the input, or its parent is used
    cap: float = 3.0  # robust z is winsorized to ±cap
    low_below: float = 35.0  # band cut-off (a guess): low below it
    high_above: float = 65.0  # band cut-off (a guess): high above it, medium between


CONFIG = Config()
VERSION, _ = version(CONFIG)  # `{revision:03d}-{hash12}` (DEC-306 d)


class Row(Protocol):
    """A `shp_sellers` row: a `Feature` or its model."""

    @property
    def product_id(self) -> UUID: ...
    @property
    def features(self) -> dict[str, Any] | None: ...
    @property
    def gap_flags(self) -> dict[str, Any] | None: ...


class Saturation(NamedTuple):
    value: float | None  # 0–100, higher is more crowded; None: insufficient signal
    band: Band | None
    explanation: Explanation | None
    reason: str | None = None  # why there is no value


def band(value: float) -> Band:
    if value < CONFIG.low_below:
        return "low"
    return "high" if value > CONFIG.high_above else "medium"


def saturation_scores(
    rows: Iterable[Row], categories: Mapping[UUID, Sequence[int]]
) -> dict[UUID, Saturation]:
    """How crowded each product already is on day t, 0–100: higher is more saturated.

    `categories` holds every product to score: its category and that category's ancestors,
    nearest first (empty when it has none). `rows` are day t's `shp_sellers` feature rows.
    Each input is a robust z within the product's category, falling back up its ancestors to
    every product (Score Definitions §4):
    - shp_sellers: ln(1 + s), s the stores with a live listing of it, counting every tracked
      store: "9 stores sell this" holds whenever they were added. Required.
    - shp_seller_g28: ln((p_t + 1) / (p_t−28 + 1)) over the stable panel, the stores tracked
      since t−28 alone, so a batch of newly tracked stores never reads as growth.
    - ads_active: no source yet, so always missing.

    T = Σ w × z / Σ w over the present inputs: a missing one gets weight 0 and the rest
    renormalise (DEC-040). Saturation = clamp(50 + 50 × T / 3, 0, 100), banded low below
    `low_below`, high above `high_above`, medium between.

    No value, with its reason, never 0:
    - no seller count: the product has no `shp_sellers` row, or one written before them.
    - seller counts don't vary: no category, nor the whole set, has a spread to normalise by.
    """
    inputs = {row.product_id: row for row in rows}
    features = {p: inputs[p].features or {} for p in categories if p in inputs}
    flags = {p: inputs[p].gap_flags or {} for p in features}

    def present(name: str) -> dict[UUID, float]:
        return {p: v for p, f in features.items() if (v := f.get(name)) is not None}

    level = {p: math.log1p(s) for p, s in present("shp_sellers").items()}
    raws = {"shp_sellers": level, "shp_seller_g28": present("shp_seller_g28")}
    zs = {k: robust_z(v, categories, min_n=CONFIG.min_n, cap=CONFIG.cap) for k, v in raws.items()}

    def seller_input(name: str, product: UUID, gap: bool) -> Component:
        found = zs[name].get(product)
        return Component(
            name=name,
            family="shp_sellers",
            source="shopify_stores",
            weight=getattr(CONFIG, name),
            raw=raws[name].get(product),
            z=found[0] if found else None,
            normalization=found[1] if found else None,
            missing=found is None,
            gap=gap,
        )

    scores = {}
    for product in categories:
        if product not in level:
            scores[product] = Saturation(None, None, None, "no seller count")
            continue
        if product not in zs["shp_sellers"]:
            scores[product] = Saturation(None, None, None, "seller counts don't vary")
            continue
        components = [
            seller_input("shp_sellers", product, False),  # a count at the cutoff: no window
            seller_input("shp_seller_g28", product, bool(flags[product].get("missed_runs"))),
            Component(
                name="ads_active", family="ads", source=None, weight=CONFIG.ads_active, missing=True
            ),
        ]
        total, explanation = explain(CONFIG, components)
        assert total is not None  # the seller count is present
        value = min(100.0, max(0.0, 50 + 50 * total / 3))
        panel = features[product].get("panel_size")
        scores[product] = Saturation(
            value, band(value), explanation.model_copy(update={"panel_size": panel})
        )
    return scores
