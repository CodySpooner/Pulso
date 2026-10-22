"""Release a finished Orca worker worktree so Windows lets Orca delete it.

    uv run --with psutil python infra/scripts/release_worktree.py <worktree path> [--dry-run]

Windows refuses to delete a folder that a running process uses as its working directory, so
`orca worktree rm` fails with EBUSY ("Delete failed" in Orca's sidebar). Two kinds of process stay
behind in a worker's folder after it finishes: the Orca terminal shell, and helpers the Codex
daemon starts for each session (MCP servers, node_repl). This script refuses anything that could
lose work, closes the workspace's Orca terminals, stops every process still inside the folder, then
removes the worktree and its folder.
"""

import argparse
import importlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ID = "8f52a451-9501-439a-ac12-e886e441a93a"
WORKSPACES = Path.home() / "orca" / "workspaces" / "pulso"
PROTECTED = {"pulso-lead", "pulso-lead-codex", ".lead-lock"}  # lead workspaces and the lead lock


def is_inside(child: Path, parent: Path) -> bool:
    child, parent = child.resolve(), parent.resolve()
    return child == parent or parent in child.parents


def path_refusal(path: Path, workspaces: Path = WORKSPACES) -> str | None:
    """Why `path` is not a releasable worker folder, or None when it is."""
    path = path.resolve()
    if path.parent != workspaces.resolve():
        return f"{path} is not a worker worktree directly under {workspaces}"
    if path.name in PROTECTED:
        return f"{path.name} is protected"
    return None


def git(path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)


def is_worktree(path: Path) -> bool:
    top = git(path, "rev-parse", "--show-toplevel")
    return top.returncode == 0 and Path(top.stdout.strip()).resolve() == path.resolve()


def work_refusal(path: Path, base: str = "origin/main") -> str | None:
    """Why releasing `path` could lose work, or None when nothing would be lost."""
    if not path.exists():
        return None
    if not is_worktree(path):
        # Git already unregistered it; only an empty skeleton is safe to delete.
        if any(p.is_file() for p in path.rglob("*")):
            return f"{path} is not a git worktree but still contains files"
        return None
    if git(path, "status", "--porcelain").stdout.strip():
        return f"{path} has uncommitted changes"
    if git(path, "merge-base", "--is-ancestor", "HEAD", base).returncode != 0:
        return f"{path} has commits that are not in {base}"
    return None


def holders(path: Path) -> list[Any]:
    """Processes whose working directory is inside `path` (needs psutil)."""
    psutil = importlib.import_module("psutil")
    found = []
    for proc in psutil.process_iter():
        try:
            if proc.pid != psutil.Process().pid and is_inside(Path(proc.cwd()), path):
                found.append(proc)
        except psutil.Error, OSError:
            continue
    return found


def stop(procs: list[Any]) -> list[str]:
    psutil = importlib.import_module("psutil")
    victims: dict[int, Any] = {}
    for proc in procs:
        try:
            for p in [*proc.children(recursive=True), proc]:
                victims[p.pid] = p
        except psutil.Error:
            continue
    stopped = []
    for p in victims.values():
        try:
            name = p.name()
            p.kill()
            stopped.append(f"{p.pid}:{name}")
        except psutil.Error:
            continue
    psutil.wait_procs(list(victims.values()), timeout=5)
    return stopped


def orca(*args: str) -> bool:
    return subprocess.run(["orca", *args, "--json"], capture_output=True, text=True).returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="report, change nothing")
    args = parser.parse_args()
    path: Path = args.path.resolve()

    refusal = path_refusal(path) or work_refusal(path)
    if refusal:
        print(json.dumps({"path": str(path), "released": False, "refused": refusal}))
        return 2
    selector = f"id:{REPO_ID}::{path.as_posix()}"
    if args.dry_run:
        found = [f"{p.pid}:{p.name()}" for p in holders(path)] if path.exists() else []
        print(json.dumps({"path": str(path), "dry_run": True, "would_stop": found}))
        return 0

    registered = is_worktree(path) if path.exists() else False
    orca("terminal", "close", "--worktree", selector, "--all")
    stopped = stop(holders(path)) if path.exists() else []
    if registered:
        orca("worktree", "rm", "--worktree", selector, "--force")
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    released = not path.exists()
    print(json.dumps({"path": str(path), "released": released, "stopped": stopped}))
    return 0 if released else 1


if __name__ == "__main__":
    sys.exit(main())
