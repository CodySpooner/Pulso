"""Source/family exclusions for future label consumers (DEC-090(e), DEC-144)."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LabelEligibility:
    available: bool
    reason: Literal["dec_090_e"] | None


def label_eligibility(*, source_key: str, family: str) -> LabelEligibility:
    """Check the observation's Source.key and demand-family name before labeling.

    `shp_inv` is the Grade A .js inventory-delta family. Every store/listing
    observed via shopify_stores is excluded for that family, even with inventory.
    Available means no exclusion here, not sufficient coverage or a chosen label
    source: consumers must still apply MSR-1 and their other eligibility checks.
    """
    if source_key == "shopify_stores" and family == "shp_inv":
        return LabelEligibility(available=False, reason="dec_090_e")
    return LabelEligibility(available=True, reason=None)
