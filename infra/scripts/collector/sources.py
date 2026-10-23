"""Collector-DB step of the guarded seeds/enable/disable ops (DEC-131).

Runs only inside the collector worker container, launched by `infra.scripts.collector` after its
checkout guards, lock and step-4 evidence gates; settings come from the container's env file.
Prints one JSON line of counts or a refusal code, never seed entries or settings.
"""

import contextlib
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.db import get_session
from pulso_core.models import Source, SourceEvent
from pulso_sources.seed_approval import SEED_SOURCES, approved_targets

# The worker image copies infra/scripts/{seeds,collector}; same import path as the host CLI.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seeds import load_seeds  # noqa: E402

SOURCES = ("fx_frankfurter", *SEED_SOURCES.values())
ACTOR = "collector-cli"


def seeds(session: Session, payload: dict[str, dict[str, Any]]) -> dict[str, Any]:
    # The loader prints a seed diff, which would include the owner's private domains.
    with contextlib.redirect_stdout(io.StringIO()):
        changed = load_seeds(session, payload, apply=True)
    counts = {
        key: {
            "entries": len(seed["entries"]),
            "enabled": sum(r["enabled"] for r in seed["entries"]),
        }
        for key, seed in payload.items()
    }
    return {"changed": changed, "sources": counts}


def locked(session: Session, key: str) -> Source:
    if key not in SOURCES:
        raise ValueError("Unknown collector source")
    return session.scalars(select(Source).where(Source.key == key).with_for_update()).one()


def enable(session: Session, key: str) -> dict[str, Any]:
    source = locked(session, key)
    if source.status == "blocked":  # only the owner's typed-reason re-enable clears a block
        return {"refused": "blocked"}
    targets = len(approved_targets(session, key)) if key in SEED_SOURCES.values() else None
    if targets == 0:
        return {"refused": "no_approved_targets"}
    if source.enabled:
        return {"changed": False, "targets": targets}
    # retry_not_before and the block count stay as they are; the framework still honours them.
    source.enabled, source.status, source.disabled_reason, source.disabled_at = (
        True,
        "active",
        None,
        None,
    )
    session.add(
        SourceEvent(
            source_id=source.id,
            actor=ACTOR,
            action="enable",
            reason="Lead Playbook §6 step 4 gates passed",
            at=datetime.now(UTC),
        )
    )
    return {"changed": True, "targets": targets}


def disable(session: Session, key: str) -> dict[str, Any]:
    source = locked(session, key)
    if not source.enabled:
        return {"changed": False}
    now = datetime.now(UTC)
    source.enabled, source.status = False, "disabled"
    source.disabled_reason, source.disabled_at = ACTOR, now
    session.add(SourceEvent(source_id=source.id, actor=ACTOR, action="disable", at=now))
    return {"changed": True}


def main(argv: list[str] | None = None) -> int:
    op, *args = sys.argv[1:] if argv is None else argv
    with get_session() as session, session.begin():
        if op == "seeds":
            result = seeds(session, json.load(sys.stdin))
        elif op == "enable":
            result = enable(session, *args)
        elif op == "disable":
            result = disable(session, *args)
        else:
            raise ValueError("Unknown operation")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
