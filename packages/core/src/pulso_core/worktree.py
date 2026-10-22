"""Shared collector/Beat guard; check both cwd and the installed caller's path."""

from pathlib import Path


def is_linked_worktree(module_path: str) -> bool:
    return any(
        (path / ".git").is_file()
        for root in (Path.cwd().resolve(), Path(module_path).resolve().parent)
        for path in (root, *root.parents)
    )
