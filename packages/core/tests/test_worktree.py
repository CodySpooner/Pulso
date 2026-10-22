from pathlib import Path

import pytest

from pulso_core.worktree import is_linked_worktree


@pytest.mark.parametrize("origin", ["cwd", "module"])
def test_worktree_detection_checks_both_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, origin: str
) -> None:
    nested = tmp_path / "linked" / "apps" / "workers"
    nested.mkdir(parents=True)
    (tmp_path / "linked" / ".git").write_text("gitdir: unused", encoding="utf-8")
    monkeypatch.chdir(nested if origin == "cwd" else tmp_path)
    module = nested if origin == "module" else tmp_path
    assert is_linked_worktree(str(module / "worker.py"))


def test_main_checkout_is_not_a_linked_worktree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    assert not is_linked_worktree(str(tmp_path / "worker.py"))
