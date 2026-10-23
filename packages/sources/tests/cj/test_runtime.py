import json
import time
from datetime import timedelta
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

import pulso_sources.cj.auth as auth_module
import pulso_sources.cj.transport as transport_module
from pulso_core.models import RawPayload, Source
from pulso_sources import framework
from pulso_sources.cj import category_plan, collect
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.categories import resolve
from pulso_sources.cj.errors import CJError
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import Request, Response, Target, enqueue_run

from .test_cj import AT, fixture
from .test_persistence import settings


def test_redis_cache_reuse_key_isolation_and_refresh_skew() -> None:
    cfg, cache = settings(), Mock()
    cfg.cj_api_key = SecretStr("fixture-key")
    cache.get.return_value = None
    post = Mock(side_effect=[Response(fixture("auth")), Response(fixture("refresh"))])
    first = Auth(cfg, now=lambda: AT, cache=cache)
    assert first.token(post) == "fixture-access"
    cache.get.return_value = cache.set.call_args.args[1]
    assert cache.set.call_args.kwargs["ex"] == 24 * 3600 - 300
    second = Auth(cfg, now=lambda: AT + timedelta(minutes=54), cache=cache)
    assert second.token(post) == "fixture-access" and post.call_count == 1
    second.now = lambda: AT + timedelta(minutes=55)
    assert second.token(post) == "fixture-access-refreshed"
    cfg.cj_api_key = SecretStr("other-fixture-key")
    assert Auth(cfg).cache_key != first.cache_key
    assert "fixture-key" not in first.cache_key and "fixture-access" not in repr(first.tokens)


def test_categories_use_only_returned_ids_and_feed_existing_plan() -> None:
    names = ["Computer & Office", " computer & office › office electronics "]
    resolved = resolve(fixture("categories"), names)
    expected = ["2252588B-72E3-4397-8C92-7D9967161084"]
    assert all(ids == expected for ids in resolved.values())
    targets = category_plan(fixture("categories"), names)
    assert len(targets) == 1 and list(targets[0].requests)[0].params["categoryId"] == expected[0]
    with pytest.raises(CJError, match="Unresolved CJ category seed"):
        resolve(fixture("categories"), ["Pet Supplies"])


def test_synthetic_category_expansion_and_unresolved_seed_evidence(session: Session) -> None:
    targets = category_plan(
        fixture("category_tree_synthetic"), ["Fixture Root", "Fixture Root › Fixture Group A"]
    )
    requests = list(targets[0].requests)
    assert len(requests) == 45
    assert {r.params["categoryId"] for r in requests} == {
        "test-only-a",
        "test-only-b",
        "test-only-c",
    }
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    collect(
        session, run.id, category_plan(fixture("categories"), ["Pet Supplies"]), settings=settings()
    )
    assert run.error_code == "cj_category_unresolved" and run.status == "partial"
    assert "Pet Supplies" in (run.error_message or "") and run.http_requests == 0
    assert "cj_points" not in session.get_one(Source, 2).config


@pytest.mark.parametrize("second_rejected,budget", [(False, 200), (True, 200), (False, 50)])
def test_reactive_refresh_is_once_and_accounts_for_every_attempt(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    second_rejected: bool,
    budget: int,
) -> None:
    cfg, cache = settings(), Mock()
    cfg.collectors_live, cfg.cj_requests_per_second = True, 0.5
    cfg.cj_daily_points_budget = budget
    cfg.cj_api_key = SecretStr("fixture-key")
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    cache.get.return_value = None
    monkeypatch.setattr(Redis, "from_url", Mock(return_value=cache))
    monkeypatch.setattr(auth_module, "datetime", Mock(now=lambda _: AT))
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(transport_module, "is_linked_worktree", lambda _: False)
    clock = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    token_error = Response(b'{"code":1600001,"result":false}', 200)
    responses = iter(
        [
            Response(fixture("auth"), 200),
            token_error,
            Response(fixture("refresh"), 200),
            token_error if second_rejected else Response(fixture("list_v2"), 200),
        ]
    )
    calls: list[tuple[str, str | None, float]] = []

    def http(
        self: Transport, endpoint: str, params: dict[str, str], *, token: str | None
    ) -> Response:
        assert not session.in_transaction()
        calls.append((endpoint, token, clock[0]))
        return next(responses)

    monkeypatch.setattr(Transport, "http", http)
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session,
        run.id,
        [Target("cj_catalog_panel", "fixture", [Request(params={"endpoint": "/product/listV2"})])],
        settings=cfg,
    )
    assert run.http_requests == (3 if budget == 50 else 4)
    assert run.params["cj_points_reserved"] == min(100, budget)
    assert [at for _, _, at in calls] == ([0, 2, 4] if budget == 50 else [0, 2, 4, 6])
    assert calls[1][1] == "fixture-access"
    if budget > 50:
        assert calls[3][1] == "fixture-access-refreshed"
    assert run.status == ("partial" if second_rejected or budget == 50 else "success")
    assert run.rows_inserted == (0 if second_rejected or budget == 50 else 2)
    payloads = list(session.scalars(select(RawPayload)))
    assert len(payloads) == (1 if budget == 50 else 2) and all(
        p.request == {"endpoint": "/product/listV2"} for p in payloads
    )


def test_http_wire_format_timeout_and_no_redirect(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = settings()
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    runtime = Transport(cfg, Mock(), Mock())
    connection, response = Mock(), Mock()
    response.read.return_value, response.status = b"redirect", 302
    response.getheaders.return_value = [("Location", "https://example.test/")]
    connection.getresponse.return_value = response
    factory = Mock(return_value=connection)
    monkeypatch.setattr(transport_module, "HTTPSConnection", factory)
    result = runtime.http("/product/getCategory", {}, token="fixture-access")
    factory.assert_called_once_with(
        "developers.cjdropshipping.com", timeout=cfg.collector_request_timeout_seconds
    )
    assert connection.request.call_args.args == ("GET", "/api2.0/v1/product/getCategory")
    assert connection.request.call_args.kwargs["headers"]["CJ-Access-Token"] == "fixture-access"
    assert result.status_code == 302 and connection.request.call_count == 1
    runtime.http("/authentication/getAccessToken", {"apiKey": "fixture-key"}, token=None)
    assert json.loads(connection.request.call_args.kwargs["body"]) == {"apiKey": "fixture-key"}
    assert "CJ-Access-Token" not in connection.request.call_args.kwargs["headers"]
    connection.request.side_effect = OSError("sensitive detail")
    with pytest.raises(ConnectionError, match="CJ transport failed"):
        runtime.http("/product/getCategory", {}, token="fixture-access")


def test_wait_past_deadline_never_reserves(monkeypatch: pytest.MonkeyPatch) -> None:
    before = Mock()
    runtime = Transport(settings(), before, Mock())
    runtime.deadline = time.monotonic() - 1
    with pytest.raises(CJError, match="wall-time"):
        runtime.send("/product/listV2", {}, token="fixture-access")
    before.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [
        Response(b'{"code":1600200,"result":false}', 429, headers={"Retry-After": "60"}),
        Response(b'{"code":1600200,"result":false}', 200, headers={"Retry-After": "60"}),
        None,
    ],
)
def test_auth_failure_does_not_charge_catalog_and_preserves_block_deadline(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    response: Response | None,
) -> None:
    cfg, cache = settings(), Mock()
    cfg.collectors_live, cfg.collector_block_threshold = True, 1
    cfg.cj_api_key = SecretStr("fixture-key")
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    cache.get.return_value = None
    if response is None:
        cache.get.side_effect = ConnectionError("cache unavailable")
    monkeypatch.setattr(Redis, "from_url", Mock(return_value=cache))
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(transport_module, "is_linked_worktree", lambda _: False)
    http = Mock(return_value=response)
    monkeypatch.setattr(Transport, "http", http)
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session,
        run.id,
        [Target("cj_catalog_panel", "fixture", [Request(params={"endpoint": "/product/listV2"})])],
        settings=cfg,
    )
    assert "cj_points" not in source.config and run.http_requests == int(response is not None)
    assert list(session.scalars(select(RawPayload))) == []
    assert source.enabled == (response is None)
    if response is not None:
        assert run.error_code == "cj_rate_limited" and source.retry_not_before is not None
        assert source.last_status_code == response.status_code
