import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.models import (
    ListingSnapshot,
    RawPayload,
    ShippingOption,
    Source,
    SupplierOffer,
    VariantSnapshot,
)
from pulso_sources import framework, imports
from pulso_sources.cj import collect
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.budget import PointsInfo, record_points, reserve
from pulso_sources.cj.csv import ImportAdapter
from pulso_sources.cj.errors import CJError
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import Request, Response, Target, enqueue_run

from .test_cj import fixture
from .test_persistence import settings


def test_provider_refill_reservations_and_unknown(session: Session) -> None:
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    source = session.get_one(Source, 2)
    run = enqueue_run(session, source_id=2, trigger="fixture", publish=lambda _: None)
    body = b'{"pointsInfo":{"usedToday":50000,"remaining":0,"total":50000}}'
    record_points(source, body, now)
    session.commit()
    for seconds in (0, 59, 60):
        with pytest.raises(CJError, match="cannot cover"):
            reserve(
                session,
                source,
                run,
                "/product/listV2",
                settings=settings(),
                now=now + timedelta(seconds=seconds),
            )
        assert "cj_points" not in source.config
    reserve(
        session, source, run, "/product/listV2", settings=settings(), now=now + timedelta(minutes=2)
    )
    session.commit()
    assert source.config["cj_provider_points"]["balance"] == 28000
    with Session(session.get_bind()) as later:
        with pytest.raises(CJError, match="cannot cover"):
            reserve(
                later,
                later.get_one(Source, 2),
                run,
                "/product/listV2",
                settings=settings(),
                now=now + timedelta(minutes=2),
            )
    with pytest.raises(CJError, match="current-day"):
        reserve(
            session,
            source,
            run,
            "/product/listV2",
            settings=settings(),
            now=now + timedelta(days=1),
        )
    for bad in (b"{}", b'{"pointsInfo":null}', b'{"pointsInfo":{"remaining":true}}'):
        record_points(source, bad, now)
        session.commit()
        assert source.config["cj_provider_points"] is None
        with pytest.raises(CJError, match="unknown"):
            reserve(session, source, run, "/product/listV2", settings=settings(), now=now)
    record_points(source, b'{"pointsInfo":{"usedToday":0,"remaining":10,"total":50}}', now)
    session.commit()
    reserve(
        session, source, run, "/product/listV2", settings=settings(), now=now + timedelta(hours=23)
    )
    assert source.config["cj_provider_points"]["balance"] == 0


@pytest.mark.parametrize(
    "field,value",
    [("remaining", -1), ("remaining", 51), ("usedToday", True), ("total", "50"), ("total", 0.5)],
)
def test_invalid_points(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        PointsInfo.model_validate({"usedToday": 0, "remaining": 10, "total": 50, field: value})


@pytest.mark.parametrize(
    "points,expected,calls", [(None, "cj_points_unknown", 0), (50, "cj_points_exhausted", 1)]
)
def test_provider_refuses_before_send(
    session: Session, monkeypatch: pytest.MonkeyPatch, points: int | None, expected: str, calls: int
) -> None:
    cfg = settings()
    cfg.collectors_live = True
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    source = session.get_one(Source, 2)
    source.enabled = True
    info = {"usedToday": 0, "remaining": points, "total": 50} if points is not None else None
    record_points(source, json.dumps({"pointsInfo": info}).encode(), datetime.now(UTC))
    session.commit()
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    body = json.loads(fixture("list_v2"))
    body["pointsInfo"] = {"usedToday": 50, "remaining": 0, "total": 50}
    http = Mock(return_value=Response(json.dumps(body).encode(), 200))
    monkeypatch.setattr(Transport, "http", http)
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session,
        run.id,
        [
            Target(
                "cj_catalog_panel", "fixture", [Request(params={"endpoint": "/product/listV2"})] * 2
            )
        ],
        settings=cfg,
    )
    assert run.error_code == expected and run.http_requests == http.call_count == calls
    assert source.enabled and source.consecutive_block_count == 0
    assert run.params.get("cj_points_reserved", 0) == calls * 50


def test_registered_csv_disabled_source_dates_variants_freight_and_replay(session: Session) -> None:
    body = (Path(__file__).parent / "fixtures/import.csv").read_bytes()
    run = imports.commit_import(session, "cj", body, settings=settings())
    assert run.status == "success", run.error_message
    assert run.rows_inserted == 8 and run.http_requests == 0
    listings = list(session.scalars(select(ListingSnapshot)))
    assert [(r.price_min_minor, r.price_max_minor, r.currency) for r in listings] == [
        (125, 250, "USD"),
        (300, 300, "EUR"),
    ]
    assert listings[0].observed_for == date(2026, 1, 1)
    assert listings[1].observed_for == listings[1].captured_at.date()
    variants = list(session.scalars(select(VariantSnapshot)))
    assert [r.price_minor for r in variants] == [125, 250, 300]
    assert all(r.inventory_quantity is None for r in variants)
    quotes = list(session.scalars(select(ShippingOption)))
    assert [(q.origin_country, q.cost_minor) for q in quotes] == [
        ("CN", 471),
        ("US", 200),
        ("CN", 600),
    ]
    assert quotes[0].variant_id == quotes[1].variant_id != quotes[2].variant_id
    assert all(q.destination_country == "US" and q.observed_for == date(2026, 1, 1) for q in quotes)
    offer = session.scalars(select(SupplierOffer).order_by(SupplierOffer.listing_id)).first()
    assert offer is not None and offer.moq == 2 and offer.warehouse_country is None
    payload = session.scalars(select(RawPayload)).one()
    observations: list[ListingSnapshot | VariantSnapshot | ShippingOption] = [
        *listings,
        *variants,
        *quotes,
    ]
    assert all(
        r.raw_payload_id == payload.id and r.captured_at == payload.captured_at
        for r in observations
    )
    adapter = ImportAdapter(imports.ImportData("csv", imports.parse_csv("cj", body), None))
    assert (
        adapter.upsert(
            session, adapter.parse(body), payload, parser_version=adapter.parser_version
        ).inserted
        == 0
    )
    repeated = imports.commit_import(session, "cj", body, settings=settings())
    assert repeated.status == "skipped" and repeated.rows_inserted == 0
    assert not session.get_one(Source, 2).enabled
    assert "stock" not in imports.TEMPLATES["cj"].columns
