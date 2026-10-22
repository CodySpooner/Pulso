from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from pulso_core.settings import Settings
from pulso_sources import framework
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response, fetch, slot_key


@pytest.mark.parametrize("enabled,linked", [(False, False), (False, True), (True, True)])
def test_fetch_cannot_call_live_adapter(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, enabled: bool, linked: bool
) -> None:
    settings.collectors_live = enabled
    monkeypatch.setattr(framework, "__file__", str(tmp_path / "framework.py"))
    if linked:
        (tmp_path / ".git").write_text("gitdir: unused", encoding="utf-8")
    adapter = Mock()
    with pytest.raises(CollectorsLiveDisabled):
        fetch(adapter, Request(), settings=settings)
    adapter.fetch.assert_not_called()


@pytest.mark.parametrize("mode", ["csv", "json", "fixture"])
def test_offline_fetch_never_invokes_network(settings: Settings, mode: str, tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: unused", encoding="utf-8")
    adapter = Mock()
    request = Request(body=b"fixture", mode=mode)  # type: ignore[arg-type]
    assert fetch(adapter, request, settings=settings).body == b"fixture"
    adapter.fetch.assert_not_called()


def test_enabled_fetch_passes_honest_user_agent(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(framework, "__file__", str(tmp_path / "framework.py"))
    settings.collectors_live = True
    monkeypatch.setenv("COLLECTORS_LIVE", "on")
    monkeypatch.setenv("PULSO_BOT_CONTACT", "https://example.test/bot")
    adapter = Mock()
    adapter.fetch.return_value = Response(b"fixture", 200)
    request = Request()
    assert fetch(adapter, request, settings=Settings()).status_code == 200
    adapter.fetch.assert_called_once_with(
        request, user_agent="PulsoBot/0.1 (+https://example.test/bot)"
    )


def test_slots_use_utc_date_and_iso_week() -> None:
    at = datetime(2026, 10, 21, 22, tzinfo=timezone(timedelta(hours=-4)))
    assert slot_key("catalog", at) == "catalog:2026-10-22"
    assert slot_key("freight", at, cadence="weekly") == "freight:2026-W43"
    assert (
        slot_key("freight", datetime(2027, 1, 1, tzinfo=UTC), cadence="weekly")
        == "freight:2026-W53"
    )
    for job, stamp in [("catalog", at.replace(tzinfo=None)), ("a" * 30, at), ("Bad:job", at)]:
        with pytest.raises(ValueError):
            slot_key(job, stamp)
