"""One lead at a time: an atomic lock shared by the Claude and Codex lead automations.

    uv run python infra/scripts/lead_lock.py acquire --provider claude  # token, or exit 3
    uv run python infra/scripts/lead_lock.py beat <token>               # exit 4: lock lost
    uv run python infra/scripts/lead_lock.py release <token>
    uv run python infra/scripts/lead_lock.py check                      # 0 free, 3 held

The lock is a directory created with one atomic mkdir, outside OneDrive (sync delays) and outside
every worktree. A holder acquired inside an Orca automation run records that run (DEC-214). The
holder is dead once Orca lists its run as final with the run's terminal closed, or once it stops
beating for STALE_SECONDS. If Orca can't be read, only the beat rule applies. Stdlib only.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

# Newest automation runs (every automation's when None); None when the history can't be read.
type Runs = Callable[[str | None], list[dict[str, object]] | None]

DEFAULT_LOCK_DIR = Path.home() / "orca" / "workspaces" / "pulso" / ".lead-lock"
LOCK_DIR = Path(os.environ.get("PULSO_LEAD_LOCK_DIR", DEFAULT_LOCK_DIR))
STALE_SECONDS = 20 * 60
HELD, NOT_OWNER = 3, 4
# Orca's isFinalAutomationRunStatus: a run never leaves these. Anything else counts as live.
FINAL = {
    "completed",
    "dispatch_failed",
    "skipped_precheck",
    "skipped_missed",
    "skipped_unavailable",
    "skipped_needs_interactive_auth",
}


def orca_runs(automation: str | None) -> list[dict[str, object]] | None:
    # The automation precheck may run without Orca's bin directory on PATH.
    orca = shutil.which("orca") or str(
        Path(os.environ.get("LOCALAPPDATA", ""), "Programs/orca/resources/bin/orca.exe")
    )
    cmd = [orca, "automations", "runs", "--limit", "10", "--json"]
    try:
        out = subprocess.run(
            [*cmd, "--id", automation] if automation else cmd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=True,
        ).stdout
        runs = json.loads(out)["result"]["runs"]
    except OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError:
        return None
    return [run for run in runs if isinstance(run, dict)] if isinstance(runs, list) else None


def own_run(runs: Runs) -> dict[str, object]:
    """Owner fields naming the dispatched Orca run in this terminal pane; {} outside one."""
    pane = os.environ.get("ORCA_PANE_KEY") or os.environ.get("ORCA_AGENT_PANE")
    for run in (runs(None) or []) if pane else []:
        if run.get("terminalPaneKey") == pane and run.get("status") == "dispatched":
            return {"automation": run.get("automationId"), "run": run.get("id")}
    return {}


def run_ended(owner: dict[str, object] | None, runs: Runs) -> bool:
    """True only when Orca lists the holder's run as final and has closed the run's terminal."""
    automation, run_id = (owner or {}).get("automation"), (owner or {}).get("run")
    if not isinstance(automation, str) or not isinstance(run_id, str):
        return False
    for run in runs(automation) or []:
        if run.get("id") == run_id:
            # A final run whose terminal is still open can wake up and act (2026-10-23 run 52).
            return run.get("status") in FINAL and not run.get("terminalPtyId")
    return False


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


def acquire(
    provider: str, lock: Path = LOCK_DIR, now: float | None = None, runs: Runs = orca_runs
) -> str | None:
    """Return a token, or None when another lead holds a live lock."""
    now = time.time() if now is None else now
    mine = own_run(runs)  # before mkdir: a lock dir without owner.json counts as stale
    for _ in range(2):
        try:
            lock.mkdir(parents=False)
        except FileExistsError:
            owner = _read(lock)
            if not is_stale(owner, now) and not run_ended(owner, runs):
                return None
            # ponytail: stale takeover isn't race-free; the 15-minute stagger, separate lead
            # worktrees and fast-forward-only pushes to a protected main are the backstop.
            shutil.rmtree(lock, ignore_errors=True)
            continue
        token = secrets.token_hex(8)
        _write(
            lock,
            {
                "token": token,
                "provider": provider,
                "pid": os.getpid(),
                "started": now,
                "beat": now,
                **mine,
            },
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


def held(lock: Path = LOCK_DIR, now: float | None = None, runs: Runs = orca_runs) -> bool:
    now = time.time() if now is None else now
    owner = _read(lock)
    return lock.exists() and not is_stale(owner, now) and not run_ended(owner, runs)


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
