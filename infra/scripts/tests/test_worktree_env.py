from pathlib import Path

import pytest

from worktree_env import derive

A = Path("C:/dev/pulso-worktrees/p0-spine")
B = Path("C:/dev/pulso-worktrees/p0-web")
BASE = {
    "DATABASE_URL": "postgresql+psycopg://pulso:pw@localhost:5432/pulso",
    "REDIS_URL": "redis://localhost:6379/0",
    "PULSO_SCHEDULER": "on",  # must never leak into a worktree
}


def test_two_paths_get_different_ports_databases_and_redis_dbs() -> None:
    a = derive(A, BASE, {}, [])
    b = derive(B, BASE, {}, [a])
    for key in ("API_PORT", "WEB_PORT", "DATABASE_URL", "REDIS_URL"):
        assert a[key] != b[key], key
    assert a["DATABASE_URL"] == "postgresql+psycopg://pulso:pw@localhost:5432/pulso_p0_spine"
    assert b["DATABASE_URL"].endswith("/pulso_p0_web")
    slot = int(a["PULSO_WORKTREE_SLOT"])
    assert a["API_PORT"] == str(8000 + slot)
    assert a["WEB_PORT"] == str(3000 + slot)
    assert a["REDIS_URL"] == f"redis://localhost:6379/{slot}"


def test_scheduler_and_live_collectors_always_off() -> None:
    env = derive(A, BASE, {}, [])
    assert env["PULSO_SCHEDULER"] == "off"
    assert env["COLLECTORS_LIVE"] == "off"


def test_slot_is_stable_and_skips_taken_slots() -> None:
    first = derive(A, BASE, {}, [])
    assert derive(A, BASE, {}, []) == first
    assert derive(A, BASE, first, []) == first
    taken = [{"PULSO_WORKTREE_SLOT": str(slot)} for slot in range(1, 15)]
    assert derive(A, BASE, first, taken)["PULSO_WORKTREE_SLOT"] == "15"
    with pytest.raises(SystemExit):
        derive(A, BASE, {}, [*taken, {"PULSO_WORKTREE_SLOT": "15"}])


def test_same_folder_name_elsewhere_gets_its_own_database() -> None:
    a = derive(A, BASE, {}, [])
    twin = derive(Path("D:/elsewhere/p0-spine"), BASE, {}, [a])
    assert twin["DATABASE_URL"] != a["DATABASE_URL"]


def test_works_without_a_base_env() -> None:
    env = derive(A, {}, {}, [])
    assert env["DATABASE_URL"] == "postgresql+psycopg://pulso@localhost:5432/pulso_p0_spine"
