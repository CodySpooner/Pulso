import subprocess
from pathlib import Path

from release_worktree import path_refusal, work_refusal


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(name, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", name)


def test_only_direct_children_of_the_workspaces_folder_are_releasable(tmp_path: Path) -> None:
    root = tmp_path / "workspaces"
    assert path_refusal(root / "p1-05-imports", root) is None
    assert path_refusal(root / "pulso-lead", root) == "pulso-lead is protected"
    assert path_refusal(root / "pulso-lead-codex", root) is not None
    assert path_refusal(root / ".lead-lock", root) is not None
    assert path_refusal(root / "p1-05-imports" / "apps", root) is not None
    assert path_refusal(tmp_path / "pulso", root) is not None  # e.g. the main checkout


def test_refuses_dirty_or_unmerged_worktrees(tmp_path: Path) -> None:
    repo = tmp_path / "wt"
    repo.mkdir()
    git(repo, "init", "-q")
    commit(repo, "a")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    assert work_refusal(repo) is None  # clean and merged

    (repo / "draft").write_text("wip", encoding="utf-8")
    assert "uncommitted" in (work_refusal(repo) or "")
    (repo / "draft").unlink()

    commit(repo, "b")  # not on origin/main yet
    assert "not in origin/main" in (work_refusal(repo) or "")


def test_unregistered_folders_must_be_empty_skeletons(tmp_path: Path) -> None:
    leftover = tmp_path / "p1-03"
    (leftover / "node_modules" / ".pnpm").mkdir(parents=True)
    assert work_refusal(leftover) is None
    (leftover / "notes.txt").write_text("keep me", encoding="utf-8")
    assert "still contains files" in (work_refusal(leftover) or "")
    assert work_refusal(tmp_path / "gone") is None
