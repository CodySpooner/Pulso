from dataclasses import fields, replace
from decimal import Decimal
from typing import Any

import pytest

from pulso_ml.matching.score import CONFIG, Price, combined, price_sane, route, usd_minor


@pytest.mark.parametrize(
    ("components", "expected"),
    [
        ((Decimal("0.90"), Decimal("0.90"), Decimal("0.90")), "0.9000"),
        ((Decimal("0.75"), Decimal("0.75"), Decimal("0.75")), "0.7500"),
        # 0.55 * 0.9 + 0.30 * 0.8 + 0.15 * 1.0 = 0.885
        ((Decimal("0.9"), Decimal("0.8"), Decimal("1")), "0.8850"),
        # Missing title: (0.55 * 0.92 + 0.15 * 0.84) / 0.70 = 0.902857...
        ((Decimal("0.92"), None, Decimal("0.84")), "0.9029"),
        # Image only: the weight renormalises to 1, so the score is the cosine.
        ((Decimal("0.7712"), None, None), "0.7712"),
        # Clamped to [0, 1]: opposite vectors never score below 0.
        ((Decimal("-1"), Decimal("-0.5"), Decimal("0")), "0.0000"),
    ],
)
def test_combined_score_renormalises_over_present_components(
    components: tuple[Decimal | None, Decimal | None, Decimal | None], expected: str
) -> None:
    assert combined(CONFIG, *components) == Decimal(expected)


def test_no_component_has_no_score() -> None:
    assert combined(CONFIG, None, None, None) is None


def test_float_cosines_round_to_stored_precision_before_weighting() -> None:
    # pgvector hands back float cosines; 0.89999999 is stored as 0.9000, so it scores 0.9000.
    assert combined(CONFIG, 0.89999999, None, None) == Decimal("0.9000")


@pytest.mark.parametrize(
    ("score", "sane", "expected"),
    [
        ("0.9000", True, "link"),  # exactly at auto
        ("0.8999", True, "queue"),  # just below auto
        ("1.0000", True, "link"),
        ("0.7500", True, "queue"),  # exactly at queue
        ("0.7499", True, "discard"),  # just below queue
        ("0.0000", True, "discard"),
        # An insane or unknown price never auto-links, but may still queue.
        ("0.9900", False, "queue"),
        ("0.9900", None, "queue"),
        ("0.7499", False, "discard"),
    ],
)
def test_route_thresholds(score: str, sane: bool | None, expected: str) -> None:
    assert route(CONFIG, Decimal(score), sane) == expected


def test_fixed_vectors_route_end_to_end() -> None:
    at_auto = combined(CONFIG, Decimal("0.90"), Decimal("0.90"), Decimal("0.90"))
    below_auto = combined(CONFIG, Decimal("0.9"), Decimal("0.8"), Decimal("1"))
    at_queue = combined(CONFIG, Decimal("0.75"), None, Decimal("0.75"))
    below_queue = combined(CONFIG, Decimal("0.7499"), None, None)
    assert at_auto is not None and route(CONFIG, at_auto, True) == "link"
    assert below_auto is not None and route(CONFIG, below_auto, True) == "queue"
    assert at_queue is not None and route(CONFIG, at_queue, True) == "queue"
    assert below_queue is not None and route(CONFIG, below_queue, True) == "discard"


def retail(minor: int, currency: str = "USD", rate: str | None = None) -> Price | None:
    usd = usd_minor(minor, currency, None if rate is None else Decimal(rate))
    return None if usd is None else Price(usd, supplier=False)


def cost(minor: int, currency: str = "USD", rate: str | None = None) -> Price | None:
    usd = usd_minor(minor, currency, None if rate is None else Decimal(rate))
    return None if usd is None else Price(usd, supplier=True)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (retail(1200), cost(1000), True),  # exactly 1.2x
        (retail(1199), cost(1000), False),  # just below the band
        (retail(8000), cost(1000), True),  # exactly 8x
        (retail(8001), cost(1000), False),  # just above
        (cost(1000), retail(2500), True),  # order doesn't matter
        # Two retail prices of one cost differ by at most 8 / 1.2 = 6.67x.
        (retail(1000), retail(6666), True),
        (retail(1000), retail(6700), False),
        (cost(1000), cost(1500), True),
        # Unknown or non-positive prices can't be checked.
        (retail(0), cost(1000), None),
        (None, cost(1000), None),
    ],
)
def test_price_band(a: Price | None, b: Price | None, expected: bool | None) -> None:
    assert price_sane(CONFIG, a, b) is expected


def test_cross_currency_prices_compare_in_usd_never_raw_minor_units() -> None:
    # JPY has exponent 0: 1500 JPY at 150 per USD is $10.00, the same as the $10.00 cost.
    # Raw minor units (1500 vs 1000) would read 1.5x, inside the band.
    assert usd_minor(1500, "JPY", Decimal("150")) == 1000
    assert price_sane(CONFIG, retail(1500, "JPY", "150"), cost(1000)) is False
    # KWD has exponent 3: 3.075 KWD at 0.3075 per USD is $10.00, so $20.00 retail is 2x.
    # Raw minor units (2000 vs 3075) would read 0.65x, outside the band.
    assert usd_minor(3075, "KWD", Decimal("0.3075")) == 1000
    assert price_sane(CONFIG, retail(2000), cost(3075, "KWD", "0.3075")) is True
    # No rate for a non-USD price: unknown, never a guess.
    assert usd_minor(1500, "JPY", None) is None


def test_version_is_derived_from_every_value() -> None:
    assert CONFIG.version.startswith("m3-")
    assert len(CONFIG.version) <= 80  # match_candidates.scorer_version is varchar(80)
    for field in fields(CONFIG):
        value: Any = getattr(CONFIG, field.name)
        changed: Any = value + 1 if isinstance(value, int) else value + Decimal("0.01")
        assert replace(CONFIG, **{field.name: changed}).version != CONFIG.version, field.name
    assert replace(CONFIG).version == CONFIG.version


def test_config_is_frozen_and_coherent() -> None:
    with pytest.raises(AttributeError):
        CONFIG.auto = Decimal("0.5")  # type: ignore[misc]
    assert CONFIG.image_weight + CONFIG.title_weight + CONFIG.phash_weight == 1
    assert 0 < CONFIG.queue < CONFIG.auto <= 1
    assert 1 < CONFIG.markup_low < CONFIG.markup_high
    assert CONFIG.top_k == 20
