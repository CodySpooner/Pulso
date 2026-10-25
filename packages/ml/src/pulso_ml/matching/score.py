"""Pure pair scorer: weights renormalised over present components, then a price gate (DEC-249)."""

import hashlib
from dataclasses import astuple, dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

STORED = Decimal("0.0001")  # match_candidates components and score are numeric(5,4)
Route = Literal["link", "queue", "discard"]


@dataclass(frozen=True)
class ScorerConfig:
    image_weight: Decimal
    title_weight: Decimal
    phash_weight: Decimal
    auto: Decimal
    queue: Decimal
    top_k: int
    # Retail price / supplier cost, both in USD.
    markup_low: Decimal
    markup_high: Decimal

    @property
    def version(self) -> str:
        """A hash of every value (DEC-040's rule), so changing any value is a new version."""
        return "m3-" + hashlib.sha256(repr(astuple(self)).encode()).hexdigest()[:12]


# Starting guesses until the owner-labelled set calibrates them (DEC-249).
CONFIG = ScorerConfig(
    image_weight=Decimal("0.55"),
    title_weight=Decimal("0.30"),
    phash_weight=Decimal("0.15"),
    auto=Decimal("0.90"),
    queue=Decimal("0.75"),
    top_k=20,
    markup_low=Decimal("1.2"),
    markup_high=Decimal("8"),
)


def stored(value: float | Decimal | None) -> Decimal | None:
    return None if value is None else Decimal(value).quantize(STORED, ROUND_HALF_EVEN)


def combined(
    config: ScorerConfig,
    image_cos: float | Decimal | None,
    title_cos: float | Decimal | None,
    phash_sim: float | Decimal | None,
) -> Decimal | None:
    """Weighted mean of the components present, at stored precision, clamped to [0, 1].

    Components are rounded to their stored precision first, so a stored row re-scores
    to the stored score. A missing component has weight 0 (DEC-040).
    """
    parts = [
        (weight, value)
        for weight, value in (
            (config.image_weight, stored(image_cos)),
            (config.title_weight, stored(title_cos)),
            (config.phash_weight, stored(phash_sim)),
        )
        if value is not None
    ]
    if not parts:
        return None
    total = sum((weight for weight, _ in parts), Decimal(0))
    mean = sum((weight * value for weight, value in parts), Decimal(0)) / total
    return min(max(mean.quantize(STORED, ROUND_HALF_EVEN), Decimal(0)), Decimal(1))


def route(config: ScorerConfig, score: Decimal, price_sane: bool | None) -> Route:
    """Only a checked, plausible price auto-links; an insane or unknown one may still queue."""
    if score >= config.auto and price_sane is True:
        return "link"
    return "queue" if score >= config.queue else "discard"


@dataclass(frozen=True)
class Price:
    usd_minor: int  # pulso_core.landed_cost.to_usd: never raw minor units of another currency
    supplier: bool


def price_sane(config: ScorerConfig, a: Price | None, b: Price | None) -> bool | None:
    """Retail / cost inside the markup band; None when a price is missing or not positive.

    Two retail prices (or two costs) of one product can differ by at most high / low,
    the spread the band allows between two markups of the same cost.
    """
    if a is None or b is None or a.usd_minor <= 0 or b.usd_minor <= 0:
        return None
    if a.supplier != b.supplier:
        retail, cost = (b, a) if a.supplier else (a, b)
        return config.markup_low <= Decimal(retail.usd_minor) / cost.usd_minor <= config.markup_high
    spread = Decimal(max(a.usd_minor, b.usd_minor)) / min(a.usd_minor, b.usd_minor)
    return spread <= config.markup_high / config.markup_low
