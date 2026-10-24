from collections.abc import Callable
from pathlib import Path

import pytest

from lead_lock import STALE_SECONDS, Runs, acquire, beat, held, release

AUTOMATION, PANE = "lead-automation", "tab-1:leaf-1"


@pytest.fixture(autouse=True)
def outside_orca(monkeypatch: pytest.MonkeyPatch) -> None:
    # The suite may run inside an Orca terminal: never look up its real pane.
    monkeypatch.delenv("ORCA_PANE_KEY", raising=False)
    monkeypatch.delenv("ORCA_AGENT_PANE", raising=False)


@pytest.fixture
def lead_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """This process runs in the terminal of a dispatched Orca lead run (a fake run history)."""
    monkeypatch.setenv("ORCA_PANE_KEY", PANE)
    return {
        "id": "run-65",
        "automationId": AUTOMATION,
        "status": "dispatched",
        "terminalPaneKey": PANE,
        "terminalPtyId": "pty-65",
    }


def history(run: dict[str, object]) -> Runs:
    """A fake `orca automations runs --json` that always reads the run's current state."""
    return lambda automation: [run] if automation in (None, AUTOMATION) else []


def end(run: dict[str, object], status: str = "completed") -> None:
    """Orca finalizes the run and closes its terminal."""
    run.update(status=status, terminalPaneKey=None, terminalPtyId=None)


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


def test_a_holder_whose_run_has_ended_frees_the_lock_at_once(
    tmp_path: Path, lead_run: dict[str, object]
) -> None:
    lock, runs = tmp_path / ".lead-lock", history(lead_run)
    old = acquire("claude", lock, now=0, runs=runs)
    assert old
    assert beat(old, lock, now=60)
    end(lead_run)  # run 65: Orca says completed 3 minutes after the last beat
    assert not held(lock, now=240, runs=runs)
    new = acquire("claude", lock, now=240, runs=runs)
    assert new and new != old
    assert not beat(old, lock, now=241)  # a woken leftover of the old run stops at once


def test_a_live_run_keeps_the_lock_through_15_minutes_without_a_beat(
    tmp_path: Path, lead_run: dict[str, object]
) -> None:
    lock, runs = tmp_path / ".lead-lock", history(lead_run)
    assert acquire("claude", lock, now=0, runs=runs)
    assert held(lock, now=15 * 60, runs=runs)  # e.g. a 10-minute merge check in the foreground
    assert acquire("claude", lock, now=15 * 60, runs=runs) is None


@pytest.mark.parametrize("status", ["completed", "dispatch_failed"])
def test_a_finished_run_whose_terminal_is_still_open_keeps_the_lock(
    tmp_path: Path, lead_run: dict[str, object], status: str
) -> None:
    # Orca marks a run completed once the agent goes idle, and dispatch_failed after its 6-hour
    # watch, while the agent can still wake up in its terminal and act.
    lock, runs = tmp_path / ".lead-lock", history(lead_run)
    assert acquire("claude", lock, now=0, runs=runs)
    lead_run["status"] = status
    assert acquire("claude", lock, now=60, runs=runs) is None
    end(lead_run, status)
    assert acquire("claude", lock, now=61, runs=runs)


def test_a_stale_beat_frees_the_lock_even_while_the_run_shows_dispatched(
    tmp_path: Path, lead_run: dict[str, object]
) -> None:
    lock, runs = tmp_path / ".lead-lock", history(lead_run)
    assert acquire("claude", lock, now=0, runs=runs)
    assert acquire("claude", lock, now=STALE_SECONDS - 1, runs=runs) is None
    assert acquire("claude", lock, now=STALE_SECONDS, runs=runs)


LOST_SIGNALS: dict[str, Callable[[dict[str, object]], Runs]] = {
    "unreadable": lambda run: lambda _: None,  # orca missing, timed out or printed garbage
    "run-not-listed": lambda run: lambda _: [],  # no longer in the newest history page
    "unknown-status": lambda run: history({**run, "status": "new_status", "terminalPtyId": None}),
}


@pytest.mark.parametrize("signal", LOST_SIGNALS)
def test_an_unreadable_or_missing_signal_falls_back_to_the_beat_rule(
    tmp_path: Path, lead_run: dict[str, object], signal: str
) -> None:
    lock = tmp_path / ".lead-lock"
    assert acquire("claude", lock, now=0, runs=history(lead_run))
    runs = LOST_SIGNALS[signal](lead_run)
    assert held(lock, now=STALE_SECONDS - 1, runs=runs)
    assert acquire("claude", lock, now=STALE_SECONDS - 1, runs=runs) is None
    assert acquire("claude", lock, now=STALE_SECONDS, runs=runs)


@pytest.mark.parametrize("pane", [None, "another-tab:leaf"], ids=["no-pane", "not-a-lead-run"])
def test_a_holder_that_recorded_no_run_keeps_the_beat_rule(
    tmp_path: Path, lead_run: dict[str, object], monkeypatch: pytest.MonkeyPatch, pane: str | None
) -> None:
    # An owner session, or a lead whose own run Orca didn't list at acquire time.
    if pane is None:
        monkeypatch.delenv("ORCA_PANE_KEY")
    else:
        monkeypatch.setenv("ORCA_PANE_KEY", pane)
    lock, runs = tmp_path / ".lead-lock", history(lead_run)
    assert acquire("owner", lock, now=0, runs=runs)
    end(lead_run)
    assert acquire("claude", lock, now=STALE_SECONDS - 1, runs=runs) is None
    assert acquire("claude", lock, now=STALE_SECONDS, runs=runs)


def test_a_lead_whose_orca_lookup_fails_at_acquire_keeps_the_beat_rule(
    tmp_path: Path, lead_run: dict[str, object]
) -> None:
    lock = tmp_path / ".lead-lock"
    assert acquire("claude", lock, now=0, runs=lambda _: None)
    end(lead_run)
    assert acquire("claude", lock, now=60, runs=history(lead_run)) is None
