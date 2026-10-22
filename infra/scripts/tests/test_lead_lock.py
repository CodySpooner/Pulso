from pathlib import Path

from lead_lock import STALE_SECONDS, acquire, beat, held, release


def test_one_holder_at_a_time_and_only_the_holder_can_release(tmp_path: Path) -> None:
    lock = tmp_path / ".lead-lock"
    token = acquire("claude", lock, now=1000)
    assert token
    assert acquire("codex", lock, now=1001) is None
    assert held(lock, now=1001)
    assert not release("not-the-token", lock)
    assert beat(token, lock, now=1500)
    assert release(token, lock)
    assert not held(lock, now=1501)
    assert acquire("codex", lock, now=1502)


def test_a_holder_that_stops_beating_goes_stale(tmp_path: Path) -> None:
    lock = tmp_path / ".lead-lock"
    old = acquire("claude", lock, now=0)
    assert old
    assert beat(old, lock, now=100)
    assert acquire("codex", lock, now=100 + STALE_SECONDS - 1) is None
    new = acquire("codex", lock, now=100 + STALE_SECONDS)
    assert new and new != old
    assert not beat(old, lock, now=100 + STALE_SECONDS + 1)  # the dead lead must stop at once
    assert not release(old, lock)


def test_a_lock_dir_without_owner_file_is_stale(tmp_path: Path) -> None:
    lock = tmp_path / ".lead-lock"
    lock.mkdir()
    assert not held(lock, now=0)
    assert acquire("claude", lock, now=0)
