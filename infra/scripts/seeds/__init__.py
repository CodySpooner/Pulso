"""Validate and stage versioned seed lists without enabling a source."""

import difflib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_sources.seed_approval import SEED_SOURCES, is_approved_seed

DEFAULT_SEED = Path(__file__).resolve().parents[2] / "seeds/seed_v1.yaml"


def read_seed(path: Path) -> dict[str, dict[str, Any]]:
    """Read JSON-compatible YAML with full-line comments; return per-source seeds."""
    data = json.loads(
        "\n".join(
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
    )
    required = {"approval", *SEED_SOURCES}
    if not isinstance(data, dict):
        raise ValueError("Seed file must be an object")
    if set(data) != required:
        raise ValueError(
            f"Seed sections: missing {sorted(required - set(data))}; "
            f"unknown (no source key) {sorted(set(data) - required)}"
        )
    approval = data["approval"]
    if not isinstance(approval, dict) or set(approval) != {
        "version",
        "status",
        "approved_on",
        "decision",
    }:
        raise ValueError("approval requires version, status, approved_on and decision")
    version = approval["version"]
    if not isinstance(version, str) or not re.fullmatch(r"seed_v[1-9][0-9]*", version):
        raise ValueError("approval.version must be seed_v followed by a positive integer")
    if approval["decision"] != "DEC-011" or approval["status"] not in ("draft", "approved"):
        raise ValueError("approval requires decision DEC-011 and status draft or approved")
    approved = is_approved_seed(approval)
    if (approval["status"] == "approved" and not approved) or (
        approval["status"] == "draft" and approval["approved_on"] is not None
    ):
        raise ValueError("approval.approved_on must be YYYY-MM-DD for approved, null for draft")

    seeds = {}
    for section, source_key in SEED_SOURCES.items():
        entries = data[section]
        if not isinstance(entries, list):
            raise ValueError(f"{section} must be a list")
        seen: set[str] = set()
        identity = {"stores": "domain", "cj_categories": "name", "keywords": "keyword"}[section]
        fields = {
            "stores": {"domain", "name", "enabled"},
            "cj_categories": {"name", "enabled"},
            "keywords": {"keyword", "geo", "tz", "enabled"},
        }[section]
        for i, row in enumerate(entries):
            label = f"{section}[{i}]"
            if not isinstance(row, dict) or set(row) != fields:
                raise ValueError(f"{label} requires exactly: {', '.join(sorted(fields))}")
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
            row["enabled"] = approved and row["enabled"]
        seeds[source_key] = {**approval, "entries": entries}
    return seeds


def load_seeds(
    session: Session,
    seeds: dict[str, dict[str, Any]],
    *,
    apply: bool = False,
) -> int:
    """Preview or stage config.seed changes; the caller owns commit/rollback."""
    if set(seeds) != set(SEED_SOURCES.values()):
        raise ValueError("Expected seed source keys: " + ", ".join(SEED_SOURCES.values()))
    query = select(Source).where(Source.key.in_(seeds)).order_by(Source.id)
    sources = list(session.scalars(query.with_for_update() if apply else query))
    missing = set(seeds) - {source.key for source in sources}
    if missing:
        raise ValueError(f"Missing sources: {', '.join(sorted(missing))}; apply migrations first")
    changes = []
    for source in sources:
        before, after = source.config.get("seed"), seeds[source.key]
        if before == after:
            continue
        if isinstance(before, dict) and before.get("version") == after["version"]:
            raise ValueError(f"{source.key}: changed seed content; bump approval.version")
        changes.append((source, before, after))

    for key, seed in seeds.items():
        entries = seed["entries"]
        print(f"{key}: {len(entries)} entries, {sum(row['enabled'] for row in entries)} enabled")
    for source, before, after in changes:
        # Diff only the seed block; unrelated config can contain credentials.
        print(
            "\n".join(
                difflib.unified_diff(
                    json.dumps(before, indent=2, sort_keys=True, ensure_ascii=False).splitlines(),
                    json.dumps(after, indent=2, sort_keys=True, ensure_ascii=False).splitlines(),
                    fromfile=f"{source.key}.config.seed (current)",
                    tofile=f"{source.key}.config.seed (proposed)",
                    lineterm="",
                )
            )
        )
    if apply:
        for source, _, after in changes:
            source.config = {**source.config, "seed": after}
    return len(changes)
