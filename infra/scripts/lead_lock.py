"""One lead at a time: an atomic lock shared by the Claude and Codex lead automations.

    uv run python infra/scripts/lead_lock.py acquire --provider claude  # token, or exit 3
    uv run python infra/scripts/lead_lock.py beat <token>               # exit 4: lock lost
    uv run python infra/scripts/lead_lock.py release <token>
    uv run python infra/scripts/lead_lock.py check                      # 0 free, 3 held

The lock is a directory created with one atomic mkdir, outside OneDrive (sync delays) and outside
every worktree. A holder that stops beating for STALE_SECONDS is treated as dead. Stdlib only.
"""

import argparse
import json
import os
import secrets
import shutil
import sys
import time
from pathlib import Path

DEFAULT_LOCK_DIR = Path.home() / "orca" / "workspaces" / "pulso" / ".lead-lock"
LOCK_DIR = Path(os.environ.get("PULSO_LEAD_LOCK_DIR", DEFAULT_LOCK_DIR))
STALE_SECONDS = 20 * 60
HELD, NOT_OWNER = 3, 4


def _read(lock: Path) -> dict[str, object] | None:
    try:
        data = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    return data if isinstance(data, dict) else None


def _write(lock: Path, data: dict[str, object]) -> None:
    (lock / "owner.json").write_text(json.dumps(data), encoding="utf-8")


def is_stale(owner: dict[str, object] | None, now: float) -> bool:
    beat = owner.get("beat") if owner else None
    # A lock dir without a readable heartbeat is either mid-acquire or garbage: treat it as stale.
    return not isinstance(beat, int | float) or now - beat >= STALE_SECONDS


def acquire(provider: str, lock: Path = LOCK_DIR, now: float | None = None) -> str | None:
    """Return a token, or None when another lead holds a fresh lock."""
    now = time.time() if now is None else now
    for _ in range(2):
        try:
            lock.mkdir(parents=False)
        except FileExistsError:
            if not is_stale(_read(lock), now):
                return None
            # ponytail: stale takeover isn't race-free; the 15-minute stagger, separate lead
            # worktrees and fast-forward-only pushes to a protected main are the backstop.
            shutil.rmtree(lock, ignore_errors=True)
            continue
        token = secrets.token_hex(8)
        _write(
            lock,
            {"token": token, "provider": provider, "pid": os.getpid(), "started": now, "beat": now},
        )
        return token
    return None


def beat(token: str, lock: Path = LOCK_DIR, now: float | None = None) -> bool:
    owner = _read(lock)
    if not owner or owner.get("token") != token:
        return False
    owner["beat"] = time.time() if now is None else now
    _write(lock, owner)
    return True


def release(token: str, lock: Path = LOCK_DIR) -> bool:
    owner = _read(lock)
    if not owner or owner.get("token") != token:
        return False
    shutil.rmtree(lock, ignore_errors=True)
    return True


def held(lock: Path = LOCK_DIR, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    return lock.exists() and not is_stale(_read(lock), now)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("acquire").add_argument("--provider", required=True)
    for name in ("beat", "release"):
        sub.add_parser(name).add_argument("token")
    sub.add_parser("check")
    args = parser.parse_args()

    if args.cmd == "acquire":
        token = acquire(args.provider)
        if token is None:
            print(json.dumps({"held": True, "owner": _read(LOCK_DIR)}))
            return HELD
        print(token)
        return 0
    if args.cmd == "beat":
        return 0 if beat(args.token) else NOT_OWNER
    if args.cmd == "release":
        return 0 if release(args.token) else NOT_OWNER
    return HELD if held() else 0


if __name__ == "__main__":
    sys.exit(main())
