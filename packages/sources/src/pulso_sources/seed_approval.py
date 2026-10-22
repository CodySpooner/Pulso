"""DEC-011 seed eligibility; source enablement and live-fetch checks still apply."""

import re
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Source

SEED_SOURCES = {"stores": "shopify_stores", "cj_categories": "cj", "keywords": "google_trends"}


def is_approved_seed(seed: dict[str, Any]) -> bool:
    version, approved_on = seed.get("version"), seed.get("approved_on")
    if (
        seed.get("status") != "approved"
        or seed.get("decision") != "DEC-011"
        or not isinstance(version, str)
        or not re.fullmatch(r"seed_v[1-9][0-9]*", version)
        or not isinstance(approved_on, str)
    ):
        return False
    try:
        return date.fromisoformat(approved_on).isoformat() == approved_on
    except ValueError:
        return False


def approved_targets(session: Session, source_key: str) -> list[dict[str, Any]]:
    """Read enabled targets from the current approved config.seed, failing closed."""
    if source_key not in SEED_SOURCES.values():
        return []
    config = session.scalar(select(Source.config).where(Source.key == source_key))
    seed = config.get("seed") if isinstance(config, dict) else None
    if not isinstance(seed, dict) or not is_approved_seed(seed):
        return []
    entries = seed.get("entries")
    if not isinstance(entries, list):
        return []
    return [dict(row) for row in entries if isinstance(row, dict) and row.get("enabled") is True]
