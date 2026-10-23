import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import (
    Listing,
    ListingSnapshot,
    ListingVariant,
    RawPayload,
    ShippingOption,
    Source,
    SourceEvent,
    SupplierOffer,
    VariantSnapshot,
)
from pulso_core.settings import Settings
from pulso_sources import framework, imports
from pulso_sources.cj import collect
from pulso_sources.cj.auth import Auth
from pulso_sources.cj.budget import PointsInfo, record_points, reserve
from pulso_sources.cj.csv import CSV_WRITER, ImportAdapter
from pulso_sources.cj.errors import CJError
from pulso_sources.cj.tracked import VARIANT_WRITERS, TrackedAdapter
from pulso_sources.cj.tracked import plan as tracked_plan
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import Request, Response, Target, current_fields, enqueue_run

from .test_cj import fixture
from .test_persistence import settings
from .test_variant_writers import rows as variant_rows
from .test_variant_writers import tracked_run

CATEGORIES = fixture("categories")  # The public example carries no pointsInfo.
TRACKED = {
    "/product/getCategory": CATEGORIES,
    "/product/query": fixture("detail"),
    "/product/stock/getInventoryByPid": fixture("stock"),
    "/logistic/freightCalculate": fixture("freight"),
}


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
    kept = source.config["cj_provider_points"]
    for absent in (b"{}", b"<html>502</html>", b"[]", None):  # e.g. stock, freight, error pages
        record_points(source, absent, now)
        assert source.config["cj_provider_points"] == kept
    for bad in (b'{"pointsInfo":null}', b'{"pointsInfo":{"remaining":true}}'):
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
    "points,expected,calls",
    [
        # Unknown spends only the free renewal (DEC-156); it reports no balance, so no paid send.
        (None, "cj_points_unknown", ["/product/getCategory"]),
        (50, "cj_points_exhausted", ["/product/listV2"]),
    ],
)
def test_provider_refuses_before_send(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    points: int | None,
    expected: str,
    calls: list[str],
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
    bodies = {"/product/listV2": json.dumps(body).encode(), "/product/getCategory": CATEGORIES}
    http = Mock(side_effect=lambda endpoint, *a, **kw: Response(bodies[endpoint], 200))
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
    assert run.error_code == expected and [c.args[0] for c in http.call_args_list] == calls
    assert run.http_requests == len(calls)
    assert source.enabled and source.consecutive_block_count == 0
    assert run.params.get("cj_points_reserved", 0) == calls.count("/product/listV2") * 50


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


def live(
    session: Session, monkeypatch: pytest.MonkeyPatch, bodies: dict[str, bytes]
) -> tuple[Settings, list[str]]:
    """Enabled source and a cached token; fake HTTP records each endpoint it is sent."""
    cfg = settings()
    cfg.collectors_live = True
    cfg.pulso_bot_contact = "https://example.test/bot"  # type: ignore[assignment]
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr("pulso_sources.cj.transport.is_linked_worktree", lambda _: False)
    monkeypatch.setattr(Auth, "token", lambda *a, **kw: "fixture-access")
    session.get_one(Source, 2).enabled = True
    session.commit()
    sent: list[str] = []

    def http(self: Transport, endpoint: str, params: object, *, token: str | None) -> Response:
        sent.append(endpoint)
        return Response(bodies[endpoint], 200)

    monkeypatch.setattr(Transport, "http", http)
    return cfg, sent


def without_points(name: str) -> bytes:
    body = json.loads(fixture(name))
    body.pop("pointsInfo", None)
    return json.dumps(body).encode()


def test_absent_points_info_keeps_debited_evidence(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-47 C-M1: stock and freight bodies carry no pointsInfo; all four sends proceed."""
    cfg, sent = live(session, monkeypatch, TRACKED)
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session,
        run.id,
        tracked_plan(["fixture-product"], ["fixture-variant-a"]),
        settings=cfg,
        adapter=TrackedAdapter(),
    )
    assert run.status == "success", (run.error_code, run.error_message)
    assert sent == [
        "/product/query",
        "/product/stock/getInventoryByPid",
        "/logistic/freightCalculate",
        "/logistic/freightCalculate",
    ]
    assert run.http_requests == 4 and run.params["cj_points_reserved"] == 40
    # Detail reported the full balance; the next three sends debit it locally.
    provider = session.get_one(Source, 2).config["cj_provider_points"]
    assert provider["balance"] == (50000 - 30) * 1440


def test_present_invalid_points_info_blocks_paid_sends(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = json.loads(fixture("detail"))
    detail["pointsInfo"]["remaining"] = 50001  # above total
    cfg, sent = live(
        session, monkeypatch, {**TRACKED, "/product/query": json.dumps(detail).encode()}
    )
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session, run.id, tracked_plan(["fixture-product"]), settings=cfg, adapter=TrackedAdapter()
    )
    # The one free renewal reports no balance, so stock is refused before HTTP.
    assert sent == ["/product/query", "/product/getCategory"]
    assert run.error_code == "cj_points_unknown" and run.http_requests == 2
    assert run.params["cj_points_reserved"] == 10
    assert session.get_one(Source, 2).config["cj_provider_points"] is None


@pytest.mark.parametrize(
    "renewal,budget,paid,error",
    [
        ({"usedToday": 0, "remaining": 50000, "total": 50000}, 20000, 2, None),
        ({"usedToday": 40, "remaining": 10, "total": 50}, 20000, 1, "cj_points_exhausted"),
        ({"usedToday": 0, "remaining": 50000, "total": 50000}, 10, 1, "cj_daily_budget"),
        (None, 20000, 0, "cj_points_unknown"),  # stale evidence is never extrapolated
        ({"usedToday": 0, "remaining": 60, "total": 50}, 20000, 0, "cj_points_unknown"),
    ],
)
def test_next_utc_day_cached_token_renews_once_with_free_category(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    renewal: dict[str, int] | None,
    budget: int,
    paid: int,
    error: str | None,
) -> None:
    """P1-47 C-M2: yesterday's evidence and a cached token; paid bodies carry no pointsInfo."""
    source = session.get_one(Source, 2)
    record_points(source, fixture("list_v2"), datetime.now(UTC) - timedelta(days=1))
    session.commit()
    categories = json.loads(CATEGORIES)
    if renewal is not None:
        categories["pointsInfo"] = renewal
    bodies = {
        **TRACKED,
        "/product/getCategory": json.dumps(categories).encode(),
        "/product/query": without_points("detail"),
    }
    cfg, sent = live(session, monkeypatch, bodies)
    cfg.cj_daily_points_budget = budget
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session, run.id, tracked_plan(["fixture-product"]), settings=cfg, adapter=TrackedAdapter()
    )
    assert sent == [
        "/product/getCategory",
        *["/product/query", "/product/stock/getInventoryByPid"][:paid],
    ]
    assert run.error_code == error and run.http_requests == len(sent)
    assert run.params.get("cj_points_reserved", 0) == 10 * paid
    provider = session.get_one(Source, 2).config["cj_provider_points"]
    if renewal is not None and renewal["remaining"] <= renewal["total"]:
        assert provider["balance"] == (renewal["remaining"] - 10 * paid) * 1440


def test_ambiguous_sku_uses_csv_identity_and_replays(session: Session) -> None:
    """P1-47 C-M3: tracked detail later adds a real variant with the CSV row's SKU."""
    csv = b"cj_product_id,sku,name,unit_cost,currency\nfixture-csv,fixture-a,Fixture CSV,1.25,USD\n"
    assert imports.commit_import(session, "cj", csv, settings=settings()).status == "success"
    listing = session.scalars(select(Listing).filter_by(external_id="fixture-csv")).one()
    now = datetime.now(UTC)
    session.add(
        ListingVariant(
            listing_id=listing.id,
            external_id="real-vid",
            sku="fixture-a",
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    session.commit()
    changed = csv.replace(b"1.25", b"1.30")
    run = imports.commit_import(session, "cj", changed, settings=settings())
    assert run.status == "success", run.error_message
    variants = {v.external_id: v.id for v in session.scalars(select(ListingVariant))}
    prices = session.execute(
        select(VariantSnapshot.variant_id, VariantSnapshot.price_minor).order_by(VariantSnapshot.id)
    ).all()
    assert [tuple(p) for p in prices] == [
        (variants["csv-sku:fixture-a"], 125),
        (variants["csv-sku:fixture-a"], 130),
    ]
    assert imports.commit_import(session, "cj", changed, settings=settings()).status == "skipped"
    payload = session.get_one(RawPayload, run.params["raw_payload_id"])
    adapter = ImportAdapter(imports.ImportData("csv", imports.parse_csv("cj", changed), None))
    stats = adapter.upsert(
        session, adapter.parse(changed), payload, parser_version=adapter.parser_version
    )
    assert stats.inserted == 0


def test_csv_prices_are_their_own_variant_writer(session: Session) -> None:
    """DEC-120 caveat: CSV rows on a tracked variant stay change-only among CSV captures."""
    tracked_run(session)
    csv = "cj_product_id,sku,name,unit_cost,currency\nfixture-product,TEST-A,{},1.25,USD\n"
    first = imports.commit_import(session, "cj", csv.format("One").encode(), settings=settings())
    stock = json.loads(fixture("stock"))
    stock["data"]["variantInventories"][0]["inventory"][0]["totalInventory"] = 13
    tracked_run(session, json.dumps(stock).encode())  # a newer stock row in between
    second = imports.commit_import(session, "cj", csv.format("Two").encode(), settings=settings())
    assert first.status == second.status == "success"
    key, history = variant_rows(session, "fixture-variant-a")
    # Detail, stock, the first CSV price, the newer stock; the unchanged CSV price appends nothing.
    assert [r.inventory_quantity for r in history] == [None, 15, None, 16]
    detail, csv_row = history[0], history[2]
    assert csv_row.raw_payload_id == first.params["raw_payload_id"]
    current = current_fields(session, VariantSnapshot, key=key, writers=VARIANT_WRITERS)
    assert current["price_minor"].id == detail.id  # detail still owns the default read
    manual = current_fields(session, VariantSnapshot, key=key, writers=(CSV_WRITER,))
    assert manual["price_minor"].id == csv_row.id and csv_row.currency == "USD"


def test_omitted_offer_columns_preserve_existing_values(session: Session) -> None:
    """aud-008 imp-070 lead probe: a later import without moq/warehouse_country columns."""
    first = (
        b"cj_product_id,sku,name,unit_cost,currency,moq,warehouse_country\n"
        b"fixture-product,fixture-a,Fixture,2.50,USD,5,US\n"
    )
    second = (
        b"cj_product_id,sku,name,unit_cost,currency\nfixture-product,fixture-a,Fixture,2.60,USD\n"
    )
    assert imports.commit_import(session, "cj", first, settings=settings()).status == "success"
    run = imports.commit_import(session, "cj", second, settings=settings())
    assert run.status == "success", run.error_message
    offer = session.scalars(select(SupplierOffer)).one()
    assert (offer.moq, offer.warehouse_country) == (5, "US")
    key, _ = variant_rows(session, "csv-sku:fixture-a")
    manual = current_fields(session, VariantSnapshot, key=key, writers=(CSV_WRITER,))["price_minor"]
    assert (manual.price_minor, manual.raw_payload_id) == (260, run.params["raw_payload_id"])


@pytest.mark.parametrize("new_cells", ["", ",moq,warehouse_country|,,"], ids=["absent", "blank"])
def test_offer_fields_change_only_on_explicit_cells(session: Session, new_cells: str) -> None:
    """DEC-186: an absent column or blank cell is no evidence and keeps the stored value."""
    head = "cj_product_id,sku,name,unit_cost,currency"
    row = "fixture-product,fixture-a,Fixture,{}.00,USD"
    header, cells = new_cells.split("|") if new_cells else ("", "")
    steps = [
        # A new offer without MOQ evidence keeps the column's schema default of 1.
        (f"{head}{header}\n{row}{cells}", (1, None)),
        (f"{head},moq,warehouse_country\n{row},5,US", (5, "US")),
        (f"{head},moq,warehouse_country\n{row},,", (5, "US")),
        (f"{head}\n{row}", (5, "US")),
        (f"{head},moq\n{row},7", (7, "US")),
        # Only stated warehouses count: a blank row doesn't make the product multi-warehouse.
        (
            f"{head},warehouse_country\n{row},CN\nfixture-product,fixture-b,Fixture,1.00,USD,",
            (7, "CN"),
        ),
    ]
    bodies = [body.format(cost).encode() for cost, (body, _) in enumerate(steps, 1)]
    for body, (_, expected) in zip(bodies, steps, strict=True):
        run = imports.commit_import(session, "cj", body, settings=settings())
        assert run.status == "success", run.error_message
        offer = session.execute(select(SupplierOffer.moq, SupplierOffer.warehouse_country)).one()
        assert tuple(offer) == expected, body
    repeated = imports.commit_import(session, "cj", bodies[3], settings=settings())
    assert repeated.status == "skipped"
    offer = session.execute(select(SupplierOffer.moq, SupplierOffer.warehouse_country)).one()
    assert tuple(offer) == (7, "CN")
    _, history = variant_rows(session, "csv-sku:fixture-a")
    assert [r.price_minor for r in history] == [100, 200, 300, 400, 500, 600]


def test_renewal_inactivity_disables_once_without_paid_send(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = session.get_one(Source, 2)
    record_points(source, fixture("list_v2"), datetime.now(UTC) - timedelta(days=1))
    session.commit()
    disabled = json.dumps({"code": 1600014, "result": False, "message": "disabled"}).encode()
    cfg, sent = live(session, monkeypatch, {**TRACKED, "/product/getCategory": disabled})
    run = enqueue_run(session, source_id=2, trigger="manual", publish=lambda _: None)
    collect(
        session, run.id, tracked_plan(["fixture-product"]), settings=cfg, adapter=TrackedAdapter()
    )
    assert sent == ["/product/getCategory"] and run.http_requests == 1
    assert run.error_code == "cj_api_disabled_inactivity" and "cj_points_reserved" not in run.params
    assert not source.enabled and source.disabled_reason == "cj_api_disabled_inactivity"
    assert session.scalar(select(func.count()).select_from(SourceEvent)) == 1
