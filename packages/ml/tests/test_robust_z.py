import math

import pytest

from pulso_core.scores import Normalization
from pulso_ml.scores import robust_z

LEAF, PARENT, ROOT = 11, 2, 1  # a category, its parent and the root: lineage nearest first


def spread(n: int) -> list[float]:
    return [float(i % 7) for i in range(n)]  # values 0..6: a spread


def z_of(values: dict[str, float], lineage: dict[str, tuple[int, ...]]) -> dict[str, float]:
    return {k: z for k, (z, _) in robust_z(values, lineage, min_n=30, cap=3.0).items()}


def test_the_formula_is_median_and_mad_scaled_by_1_4826() -> None:
    values = {k: float(v) for k, v in zip("abcde", [1, 2, 3, 4, 5], strict=True)}
    found = robust_z(values, {}, min_n=30, cap=3.0)
    assert found["e"][0] == pytest.approx(2 / 1.4826)
    assert found["e"][1] == Normalization(category_id=None, n=5)
    assert found["a"][0] == pytest.approx(-2 / 1.4826)
    assert found["c"][0] == 0


# (products in LEAF, in PARENT outside LEAF, in ROOT outside PARENT, LEAF's values all equal,
# the category whose median and MAD are used for product "x"); x sits in LEAF.
CHAINS = [
    pytest.param(30, 0, 0, False, LEAF, id="n = 30: its own category"),
    pytest.param(29, 30, 0, False, PARENT, id="n = 29: the parent"),
    pytest.param(1, 30, 0, False, PARENT, id="a one-product category: the parent"),
    pytest.param(1, 5, 30, False, ROOT, id="a small parent: the next ancestor"),
    pytest.param(1, 5, 5, False, None, id="every level small: global"),
    pytest.param(30, 60, 0, True, PARENT, id="MAD = 0 with n = 30: the parent"),
]


@pytest.mark.parametrize(("leaf", "parent", "root", "flat", "used"), CHAINS)
def test_a_small_or_flat_category_falls_back_up_its_lineage(
    leaf: int, parent: int, root: int, flat: bool, used: int | None
) -> None:
    values: dict[str, float] = {}
    lineage: dict[str, tuple[int, ...]] = {}
    for prefix, count, chain in [
        ("leaf", leaf, (LEAF, PARENT, ROOT)),
        ("parent", parent, (PARENT, ROOT)),
        ("root", root, (ROOT,)),
    ]:
        for i, value in enumerate([5.0] * count if flat and prefix == "leaf" else spread(count)):
            values[f"{prefix}{i}"] = value
            lineage[f"{prefix}{i}"] = chain
    values["x"], lineage["x"] = values.pop("leaf0"), lineage.pop("leaf0")
    _, normalization = robust_z(values, lineage, min_n=30, cap=3.0)["x"]
    cohort = {LEAF: leaf, PARENT: leaf + parent, ROOT: leaf + parent + root, None: len(values)}
    assert normalization == Normalization(category_id=used, n=cohort[used])


def test_global_is_used_whatever_its_n_but_never_without_a_spread() -> None:
    assert z_of({"a": 1.0, "b": 3.0}, {"a": (LEAF,), "b": (LEAF,)}) == {
        "a": pytest.approx(-1 / 1.4826),
        "b": pytest.approx(1 / 1.4826),
    }
    flat = {f"p{i}": 2.0 for i in range(40)} | {"odd": 9.0}
    assert robust_z(flat, {}, min_n=30, cap=3.0) == {}  # no z, never a guessed 0 or ±3


def test_an_uncategorised_product_reads_global_while_its_neighbours_keep_their_category() -> None:
    values = {f"p{i}": v for i, v in enumerate(spread(30))} | {"orphan": 6.0, "far": 100.0}
    lineage = {f"p{i}": (LEAF,) for i in range(30)}
    found = robust_z(values, lineage, min_n=30, cap=3.0)
    assert found["p0"][1] == Normalization(category_id=LEAF, n=30)
    assert found["orphan"][1] == Normalization(category_id=None, n=32)


def test_z_is_winsorized_to_the_cap() -> None:
    values = {f"p{i}": v for i, v in enumerate(spread(30))} | {"hi": 1e6, "lo": -1e6}
    capped = z_of(values, {})
    assert (capped["hi"], capped["lo"]) == (3.0, -3.0)
    assert all(math.isfinite(z) and abs(z) <= 3 for z in capped.values())
    assert robust_z(values, {}, min_n=30, cap=4.0)["hi"][0] == 4.0
