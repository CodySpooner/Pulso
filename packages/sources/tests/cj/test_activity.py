import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pulso_sources.cj.activity import WARN_DAYS, Evidence, Status, countdown

AT = datetime(2026, 10, 1, 12, tzinfo=UTC)


def evidence(**changes: Any) -> Evidence:
    data: dict[str, Any] = {
        "kind": "owner_entry",
        "transaction_at": AT,
        "observed_at": AT,
        "amount_minor": 1999,
        "currency": "USD",
    } | changes
    return Evidence.model_validate(data)


def test_no_evidence_is_unknown_with_no_number() -> None:
    assert countdown(None, AT) == Status("unknown", None)


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (0, Status("ok", 30)),
        (30 - WARN_DAYS - 1, Status("ok", WARN_DAYS + 1)),
        (30 - WARN_DAYS, Status("warn", WARN_DAYS)),
        (29, Status("warn", 1)),
        (30, Status("expired", 0)),
        (45, Status("expired", -15)),
    ],
)
def test_countdown_boundaries(days: int, expected: Status) -> None:
    assert countdown(evidence(), AT + timedelta(days=days)) == expected


def test_days_are_utc_calendar_dates() -> None:
    late = evidence(transaction_at="2026-10-01T23:59:59Z", observed_at="2026-10-01T23:59:59Z")
    assert countdown(late, datetime(2026, 10, 2, 0, 0, 1, tzinfo=UTC)) == Status("ok", 29)
    # 2026-10-02 07:00 at +08:00 is still 2026-10-01 in UTC.
    local = evidence(transaction_at="2026-10-02T07:00:00+08:00", observed_at="2026-10-02T00:00Z")
    assert local.transaction_at == datetime(2026, 10, 1, 23, tzinfo=UTC)
    # 2026-10-31 07:00 at +08:00 is still 2026-10-30 in UTC: one day left, not expired.
    now = datetime(2026, 10, 31, 7, tzinfo=timezone(timedelta(hours=8)))
    assert countdown(local, now) == Status("warn", 1)


def test_evidence_observed_after_now_is_unknown() -> None:
    assert countdown(evidence(observed_at=AT + timedelta(days=1)), AT) == Status("unknown", None)


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError):
        countdown(None, datetime(2026, 10, 1))


@pytest.mark.parametrize(
    "changes",
    [
        {"transaction_at": datetime(2026, 10, 1)},
        {"observed_at": datetime(2026, 10, 1)},
        {"amount_minor": 0},
        {"amount_minor": -1},
        {"amount_minor": "1999"},
        {"amount_minor": True},
        {"currency": "usd"},
        {"currency": "US"},
        {"transaction_at": AT + timedelta(seconds=1)},
        {"kind": "token_issuance"},
        {"kind": "auth_response"},
        {"kind": "api_order"},
        {"accessToken": "fixture"},
    ],
)
def test_invalid_evidence_is_rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        evidence(**changes)


def test_token_issuance_is_not_evidence() -> None:
    auth = json.loads((Path(__file__).parent / "fixtures" / "auth.json").read_bytes())
    for body in (auth, auth["data"]):
        with pytest.raises(ValidationError):
            Evidence.model_validate(body)


def test_evidence_is_immutable() -> None:
    with pytest.raises(ValidationError):
        evidence().amount_minor = 1  # type: ignore[misc]
