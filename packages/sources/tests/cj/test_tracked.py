import json
from dataclasses import replace
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import ListingSnapshot, RawPayload, ShippingOption, Source, VariantSnapshot
from pulso_sources import framework, storage
from pulso_sources.cj import collect, dry_run
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.budget import POINTS
from pulso_sources.cj.tracked import TrackedAdapter, parse, plan
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response, Target, enqueue_run
from pulso_sources.storage import JsonValue

from .test_cj import fixture
from .test_persistence import settings


def test_observations_replay_and_changed_capture(session: Session) -> None:
    adapter = TrackedAdapter()
    targets = plan(["fixture-product"], ["fixture-variant-a"])
    bodies = {
        "/product/query": fixture("detail"),
        "/product/stock/getInventoryByPid": fixture("stock"),
        "/logistic/freightCalculate": fixture("freight"),
    }
    targets = [
        Target(
            t.scope,
            t.target_id,
            [
                replace(r, mode="fixture", body=bodies[str(r.params["endpoint"])])
                for r in t.requests
            ],
        )
        for t in targets
    ]
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    collect(session, run.id, targets, settings=settings(), adapter=adapter)
    assert run.status == "success" and run.rows_inserted == 11 and run.http_requests == 0
    rows = list(session.scalars(select(VariantSnapshot)))
    assert [r.price_minor for r in rows] == [125, 250, None, None]
    assert [r.inventory_quantity for r in rows] == [None, None, 15, None]
    quotes = list(session.scalars(select(ShippingOption)))
    assert [q.cost_minor for q in quotes] == [471, 600, 0] * 2
    assert quotes[0].min_days == 7 and quotes[0].max_days == 12
    assert quotes[2].min_days is None and quotes[2].max_days is None
    assert {q.origin_country for q in quotes} == {"CN", "US"}
    assert all(q.destination_country == "US" and q.quantity == 1 for q in quotes)
    for payload in session.scalars(select(RawPayload)):
        assert (
            adapter.upsert(
                session,
                parse(storage.read_capture(payload)),
                payload,
                parser_version=adapter.parser_version,
            ).inserted
            == 0
        )
    observations = [*rows, *quotes, *session.scalars(select(ListingSnapshot))]
    assert all(
        r.captured_at
        and r.observed_for == r.captured_at.date()
        and r.raw_payload_id
        and r.currency == "USD"
        for r in observations
    )
    changed = json.loads(fixture("stock"))
    changed["data"]["variantInventories"][0]["inventory"][0]["totalInventory"] = 13
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    request = Request(
        mode="fixture", params={"pid": "fixture-product"}, body=json.dumps(changed).encode()
    )
    collect(
        session,
        run.id,
        [Target("cj_tracked", "changed", [request])],
        settings=settings(),
        adapter=adapter,
    )
    assert run.status == "success" and rows[2].inventory_quantity == 15
    assert list(session.scalars(select(VariantSnapshot)))[-1].inventory_quantity == 16
    assert not session.get_one(Source, 2).enabled


@pytest.mark.parametrize("price", ["-1", "3-2", "NaN", "1.005", "1-2-3", "92233720368547758.08"])
def test_invalid_detail_money_writes_no_observations(session: Session, price: str) -> None:
    body = json.loads(fixture("detail"))
    body["data"]["sellPrice"] = price
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    request = Request(
        mode="fixture", params={"pid": "fixture-product"}, body=json.dumps(body).encode()
    )
    collect(
        session,
        run.id,
        [Target("cj_tracked", "bad", [request])],
        settings=settings(),
        adapter=TrackedAdapter(),
    )
    assert run.status == "partial" and run.rows_inserted == 0
    assert not list(session.scalars(select(ListingSnapshot)))
    assert not list(session.scalars(select(VariantSnapshot)))


def test_plan_caps_and_invalid_payloads() -> None:
    requests = [
        r
        for t in plan([str(i) for i in range(300)], [str(i) for i in range(150)])
        for r in t.requests
    ]
    assert len(requests) == 900 and sum(POINTS[str(r.params["endpoint"])] for r in requests) == 9000
    assert dry_run(10) == 16500
    for products, variants in [
        (["x"] * 2, []),
        ([str(i) for i in range(301)], []),
        ([], [str(i) for i in range(151)]),
    ]:
        with pytest.raises(ValueError):
            plan(products, variants)
    bad = json.loads(fixture("stock"))
    bad["data"]["variantInventories"][0]["inventory"][0]["totalInventory"] = -1
    with pytest.raises(ValueError):
        parse(json.dumps(bad).encode())
    bad = json.loads(fixture("detail"))
    bad["data"]["variants"].append(bad["data"]["variants"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        parse(json.dumps(bad).encode())


def test_paid_send_reservations_and_freight_wire(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = settings()
    cfg.collectors_live, cfg.cj_daily_points_budget = True, 10
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    source = session.get_one(Source, 2)
    source.enabled = True
    session.commit()

    def http(*args: object, **kwargs: object) -> Response:
        assert not session.in_transaction() and source.config["cj_points"]["reserved"] == 10
        return Response(fixture("detail"), 200)

    with monkeypatch.context() as patch:
        patch.setattr(Transport, "http", http)
        run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
        collect(session, run.id, plan(["fixture-product"]), settings=cfg, adapter=TrackedAdapter())
    assert run.http_requests == 1 and run.error_code == "cj_daily_budget"
    assert run.params["cj_points_reserved"] == 10 and run.rows_inserted == 3
    connection, response = Mock(), Mock()
    connection.getresponse.return_value = response
    response.read.return_value, response.status, response.getheaders.return_value = b"{}", 200, []
    monkeypatch.setattr("pulso_sources.cj.transport.HTTPSConnection", Mock(return_value=connection))
    request = list(plan([], ["fixture-variant-a"])[0].requests)[0]
    transport = Transport(cfg, Mock(), Mock())
    transport.fetch(request)
    assert connection.request.call_args.args == ("POST", "/api2.0/v1/logistic/freightCalculate")
    assert json.loads(connection.request.call_args.kwargs["body"])["products"] == [
        {"vid": "fixture-variant-a", "quantity": 1}
    ]
    for live, worktree in [(False, False), (True, True)]:
        cfg.collectors_live = live
        monkeypatch.setattr(
            "pulso_sources.cj.transport.is_linked_worktree", Mock(return_value=worktree)
        )
        with pytest.raises(CollectorsLiveDisabled):
            transport.fetch(request)
    cfg.collectors_live = True
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    invalid_requests: list[dict[str, JsonValue]] = [
        {"endCountryCode": "CA"},
        {"startCountryCode": "GB"},
        {"products": [{"vid": "fixture-variant-a", "quantity": 2}]},
    ]
    for invalid in invalid_requests:
        with pytest.raises(ValueError):
            transport.fetch(replace(request, params={**request.params, **invalid}))
    assert connection.request.call_count == 1
