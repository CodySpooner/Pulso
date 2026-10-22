"""DEC-011 seed eligibility; source enablement and live-fetch checks still apply."""

import re
from datetime import UTC, date, datetime
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
        approved_date = date.fromisoformat(approved_on)
        return (
            approved_date.isoformat() == approved_on and approved_date <= datetime.now(UTC).date()
        )
    except ValueError:
        return False


def validate_seed_entries(section: str, entries: Any) -> list[dict[str, Any]]:
    """Validate a whole section and return normalized copies, leaving stored config alone."""
    if not isinstance(entries, list):
        raise ValueError(f"{section} must be a list")
    seen: set[str] = set()
    identity = {"stores": "domain", "cj_categories": "name", "keywords": "keyword"}[section]
    fields = {
        "stores": {"domain", "name", "enabled"},
        "cj_categories": {"name", "enabled"},
        "keywords": {"keyword", "geo", "tz", "enabled"},
    }[section]
    validated = []
    for i, entry in enumerate(entries):
        label = f"{section}[{i}]"
        if not isinstance(entry, dict) or set(entry) != fields:
            raise ValueError(f"{label} requires exactly: {', '.join(sorted(fields))}")
        row = dict(entry)
        for field in fields - {"enabled", "tz"}:
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError(f"{label}.{field} must be nonempty text")
        if not isinstance(row["enabled"], bool):
            raise ValueError(f"{label}.enabled must be true or false")
        key = " ".join(row[identity].split()).casefold()
        if section == "stores":
            key = row["domain"].strip().lower()
            if len(key) > 253 or not re.fullmatch(
                r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", key
            ):
                raise ValueError(f"{label}.domain must be a bare domain (no scheme or path)")
            row["domain"] = key
        if key in seen:
            raise ValueError(f"{label}: duplicate {identity}: {key}")
        seen.add(key)
        if section == "keywords":
            if row["geo"] != "US":
                raise ValueError(f"{label}.geo must be US")
            if type(row["tz"]) is not int or row["tz"] != 0:
                raise ValueError(f"{label}.tz must be 0 (UTC)")
        validated.append(row)
    return validated


def approved_targets(session: Session, source_key: str) -> list[dict[str, Any]]:
    """Read enabled targets from the current approved config.seed, failing closed."""
    section = next((name for name, key in SEED_SOURCES.items() if key == source_key), None)
    if section is None:
        return []
    config = session.scalar(select(Source.config).where(Source.key == source_key))
    seed = config.get("seed") if isinstance(config, dict) else None
    if not isinstance(seed, dict) or not is_approved_seed(seed):
        return []
    try:
        entries = validate_seed_entries(section, seed.get("entries"))
    except ValueError:
        return []
    return [row for row in entries if row["enabled"]]
