"""Heuristic scores (SPEC §7, vault Intelligence/Score Definitions): pure maths, no tables."""

from collections import defaultdict
from collections.abc import Hashable, Mapping, Sequence
from statistics import median

from pulso_core.scores import Normalization

MAD_SD = 1.4826  # 1.4826 × MAD estimates the standard deviation of normal data


def robust_z[K: Hashable](
    values: Mapping[K, float], lineage: Mapping[K, Sequence[int]], *, min_n: int, cap: float
) -> dict[K, tuple[float, Normalization]]:
    """Each item's (x − median) / (1.4826 × MAD), winsorized to ±cap (Score Definitions §4).

    `lineage` holds an item's category and its ancestors, nearest first; an item without one reads
    global. The median and MAD are taken over the items with a value in the nearest of those
    categories with at least `min_n` of them and MAD > 0, else over every item (global, whatever
    its n). An item with no spread at any level gets no z, never a guessed one.
    """
    cohorts: defaultdict[int | None, list[float]] = defaultdict(list)
    for key, x in values.items():
        for category in (*lineage.get(key, ()), None):
            cohorts[category].append(x)
    stats = {}
    for category, xs in cohorts.items():
        middle = median(xs)
        stats[category] = middle, median(abs(x - middle) for x in xs)
    found = {}
    for key, x in values.items():
        for category in (*lineage.get(key, ()), None):
            middle, mad = stats[category]
            if mad > 0 and (len(cohorts[category]) >= min_n or category is None):
                z = max(-cap, min(cap, (x - middle) / (MAD_SD * mad)))
                found[key] = z, Normalization(category_id=category, n=len(cohorts[category]))
                break
    return found
