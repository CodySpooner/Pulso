import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRun, Source
from pulso_core.settings import Settings
from pulso_sources.cj import CJAdapter, dry_run, parse, plan
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.auth import parse as parse_auth
from pulso_sources.cj.budget import reserve
from pulso_sources.cj.errors import CJError, classify_error
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response, fetch

FIXTURES = Path(__file__).parent / "fixtures"
AT = datetime(2026, 10, 22, tzinfo=UTC)


def fixture(name: str) -> bytes:
    return (FIXTURES / f"{name}.json").read_bytes()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url=SecretStr("postgresql://fixture"),
        s3_access_key_id="fixture",
        s3_secret_access_key=SecretStr("fixture"),
        cj_api_key=SecretStr("fixture-key"),
    )


def test_catalog_and_empty_parse() -> None:
    a, b = parse(fixture("list_v2"))
    assert (a.price_min_minor, a.price_max_minor, a.listed_count) == (125, 250, 17)
    assert b.price_min_minor == b.price_max_minor == 310
    assert b.listed_count is None
    assert parse(fixture("empty")) == []


@pytest.mark.parametrize("price", ["-1", "3-2", "NaN", "1.005", "1-2-3", ""])
def test_invalid_money_fails(price: str) -> None:
    payload = json.loads(fixture("list_v2"))
    payload["data"]["content"][0]["productList"][0]["sellPrice"] = price
    with pytest.raises(ValueError):
        parse(json.dumps(payload).encode())


def test_errors_have_distinct_safe_codes() -> None:
    codes = set()
    for case in json.loads(fixture("errors")):
        error = classify_error(Response(json.dumps(case["body"]).encode(), case["status"]))
        assert error is not None and error.code == case["expected"]
        assert error.disable == (
            case["expected"] in {"cj_ip_user_limit", "cj_api_disabled_inactivity"}
        )
        assert "fixture" not in str(error)
        codes.add(error.code)
    assert len(codes) == 5


def test_auth_expiry_refresh_uses_fake_clock(settings: Settings) -> None:
    now = AT
    auth = Auth(settings, now=lambda: now)
    post = Mock(side_effect=[Response(fixture("auth")), Response(fixture("refresh"))])
    assert auth.token(post) == "fixture-access"
    assert post.call_args.args == ("/authentication/getAccessToken", {"apiKey": "fixture-key"})
    now += timedelta(minutes=59)
    assert auth.token(post) == "fixture-access" and post.call_count == 1
    now += timedelta(minutes=1)
    assert auth.token(post) == "fixture-access-refreshed"
    assert post.call_args.args == (
        "/authentication/refreshAccessToken",
        {"refreshToken": "fixture-refresh"},
    )
    assert "fixture-access" not in repr(auth.tokens)


def test_expired_refresh_uses_key_and_does_not_loop(settings: Settings) -> None:
    auth = Auth(settings, now=lambda: AT + timedelta(days=2))
    auth.tokens = parse_auth(fixture("auth"))
    post = Mock(return_value=Response(fixture("auth")))
    with pytest.raises(CJError, match="expired token"):
        auth.token(post)
    assert post.call_count == 1 and post.call_args.args[0].endswith("getAccessToken")


def test_auth_requires_timezone() -> None:
    payload = json.loads(fixture("auth"))
    payload["data"]["accessTokenExpiryDate"] = "2026-10-22T01:00:00"
    with pytest.raises(ValidationError):
        parse_auth(json.dumps(payload).encode())


def test_seed_projection_and_plan(caplog: pytest.LogCaptureFixture) -> None:
    root = Path(__file__).resolve().parents[4]
    seed = (root / "infra/seeds/seed_v1.yaml").read_text(encoding="utf-8")
    count = len(
        json.loads("\n".join(line for line in seed.splitlines() if not line.startswith("#")))[
            "cj_categories"
        ]
    )
    with caplog.at_level("INFO"):
        assert dry_run(count) == 16500 < 20000
    assert caplog.records[-1].projected_points == 16500  # type: ignore[attr-defined]
    targets = plan(["fixture-category"])
    requests = [r for target in targets for r in target.requests]
    assert len(requests) == 15
    assert sum(r.params.get("countryCode") == "US" for r in requests) == 3
    assert requests[0].params["orderBy"] == 1 and requests[10].params["orderBy"] == 3
    with pytest.raises(ValueError):
        dry_run(20)


def test_quota_reservation_and_utc_reset(settings: Settings) -> None:
    session = Mock(spec=Session)
    source = Source(id=2, key="cj", config={"seed": {"preserved": True}})
    run = CollectorRun(source_id=2, params={})
    settings.cj_daily_points_budget = 50
    reserve(session, source, run, "/product/listV2", settings=settings, now=AT)
    assert source.config["cj_points"] == {"day": "2026-10-22", "reserved": 50}
    assert source.config["seed"] == {"preserved": True}
    with pytest.raises(CJError, match="budget reached"):
        reserve(session, source, run, "/product/listV2", settings=settings, now=AT)
    reserve(session, source, run, "/product/listV2", settings=settings, now=AT + timedelta(days=1))
    assert run.params["cj_points_reserved"] == 100
    session.commit.assert_not_called()


def test_network_unreachable_even_with_live_flag(settings: Settings) -> None:
    adapter = CJAdapter()
    assert fetch(adapter, Request(mode="fixture", body=fixture("list_v2")), settings=settings).body
    settings.collectors_live = True
    with pytest.raises(CollectorsLiveDisabled):
        fetch(adapter, Request(), settings=settings)
    with pytest.raises(CollectorsLiveDisabled):
        adapter.fetch(Request(), user_agent="fixture")
