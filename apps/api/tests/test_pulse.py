import re
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers import pulse
from pulso_core.db import Base
from pulso_core.landed_cost import Amount, Inputs, landed_cost
from pulso_core.models import (
    Alert,
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    Watchlist,
    WatchlistItem,
    Workspace,
    WorkspaceSettings,
    WorkspaceTrackedStore,
    workspace_product_economics,
)
from pulso_core.scores import Explanation, Kind, ScoreRow, Stage, write
from pulso_ml.features.demand import FEATURE_VERSION

# WF-6a (DEC-337): the Daily Pulse for UTC day D reads only captures before D + 1 00:00Z.
SHOPIFY, CJ = 1, 2  # seeded source ids; every source is seeded disabled
D = datetime.now(UTC).date() - timedelta(days=5)
Y = D - timedelta(days=1)
V1 = "000-fixture00000"
FEES = {"payment_fee_bps": 290, "payment_fee_fixed_minor": 30, "returns_bps": 500}


def at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), UTC)


AFTER = at(D + timedelta(days=1), 1)  # past D's cutoff


def test_pulse_requires_a_session(client: TestClient) -> None:
    assert client.get("/v1/pulse").status_code == 401


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def get(api: TestClient, workspace_id: UUID, **q: Any) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.get("/v1/pulse", params=q)
    assert response.status_code == 200, response.text
    return response.json()


def observe[T: Base](
    session: Session, model: type[T], source_id: int, captured: datetime, **values: Any
) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id, run_id=run.id, captured_at=captured, request={}, bytes=1,
        sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    row = model(
        captured_at=captured, raw_payload_id=payload.id, observed_for=captured.date(), **values
    )
    session.add(row)
    session.flush()
    return row


def workspace(session: Session, **settings: Any) -> UUID:
    row = Workspace(name="Workspace")
    session.add(row)
    session.flush()
    if settings:
        session.add(WorkspaceSettings(workspace_id=row.id, **settings))
        session.flush()
    return row.id


def product(session: Session, name: str, **values: Any) -> UUID:
    row = Product(name=name, **values)
    session.add(row)
    session.flush()
    return row.id


def offer(session: Session, product_id: UUID, source: int = CJ) -> int:
    owner: dict[str, Any] = {"supplier_id": None, "store_id": None}
    if source == CJ:
        supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
        session.add(supplier)
        session.flush()
        owner["supplier_id"] = supplier.id
    else:
        store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
        session.add(store)
        session.flush()
        owner["store_id"] = store.id
    listing = Listing(
        source_id=source, external_id=uuid4().hex, url="https://example.test/p", title="Offer",
        product_id=product_id, first_seen_at=at(Y - timedelta(days=30), 0), **owner,
    )  # fmt: skip
    session.add(listing)
    session.flush()
    return listing.id


def snap(session: Session, listing_id: int, captured: datetime, **values: Any) -> None:
    source = session.get_one(Listing, listing_id).source_id
    values = {"currency": "USD", "values_hash": uuid4().hex} | values
    observe(session, ListingSnapshot, source, captured, listing_id=listing_id, **values)


def score(
    session: Session, product_id: UUID, kind: Kind, day: date, value: float | None = None,
    stage: Stage | None = None, version: str = V1,
) -> None:  # fmt: skip
    explanation = Explanation(
        model_version=version, config_digest="f" * 64, components=(), missing=(), coverage=0.0
    )
    assert write(session, [ScoreRow(product_id, day, kind, value, explanation, stage)]) == 1


def slope(session: Session, product_id: UUID, day: date, value: float | None) -> None:
    session.add(
        ProductDailyFeature(
            product_id=product_id, feature_date=day, family="gt_interest",
            feature_version=FEATURE_VERSION, coverage=Decimal(1), has_gap=value is None,
            features={"gt_slope": value, "gt_keywords": 2,
                      "gt_as_of": at(day - timedelta(days=2), 9).isoformat()},
            gap_flags={"missed_runs": []},
        )
    )  # fmt: skip
    session.flush()


def alert(session: Session, workspace_id: UUID, fired: datetime, **values: Any) -> int:
    values = {"type": "supplier_price_change", "entity_type": "supplier_offer",
              "entity_id": "999999"} | values  # fmt: skip
    row = Alert(workspace_id=workspace_id, dedupe_key=uuid4().hex, fired_at=fired, payload={},
                **values)  # fmt: skip
    session.add(row)
    session.flush()
    return row.id


def watch(session: Session, workspace_id: UUID, name: str, *product_ids: UUID) -> UUID:
    row = Watchlist(workspace_id=workspace_id, name=name)
    session.add(row)
    session.flush()
    for i, product_id in enumerate(product_ids):
        session.add(
            WatchlistItem(
                workspace_id=workspace_id, watchlist_id=row.id, product_id=product_id,
                added_at=at(Y, i),
            )
        )  # fmt: skip
    session.flush()
    return row.id


def market(session: Session) -> dict[str, UUID]:
    """CJ, Trends and scores only (Shopify disabled and unseen), plus a row past D's cutoff of
    each kind."""
    lamp, fan, mat, old = (product(session, n) for n in ("Lamp", "Fan", "Mat", "Old version"))
    score(session, lamp, "trend", Y, 60.0)
    score(session, lamp, "trend", D, 71.0)
    score(session, lamp, "lifecycle", D, stage="rising")
    score(session, fan, "trend", Y, 50.0)
    score(session, fan, "trend", D, 42.0)
    score(session, fan, "lifecycle", D, stage="declining")
    score(session, mat, "trend", D, 64.0)  # no row the day before
    score(session, mat, "lifecycle", D, stage="emerging")
    score(session, old, "trend", Y, 30.0)
    score(session, old, "trend", D, 90.0, version="001-fixture00001")  # a fix, not a move
    score(session, mat, "trend", D + timedelta(days=1), 99.0)  # after the cutoff
    score(session, mat, "lifecycle", D + timedelta(days=1), stage="rising")
    lamp_offer, fan_offer = offer(session, lamp), offer(session, fan)
    snap(session, lamp_offer, at(Y, 6), price_min_minor=740)
    snap(session, lamp_offer, at(D, 6), price_min_minor=690)
    snap(session, lamp_offer, AFTER, price_min_minor=999)  # after the cutoff
    snap(session, fan_offer, at(Y, 6), price_min_minor=1200, stock=25)
    snap(session, fan_offer, at(D, 7), stock=0)  # an inventory read: stock only
    snap(session, fan_offer, AFTER, stock=40)
    mat_offer = offer(session, mat)  # stock read on both days, still in stock
    snap(session, mat_offer, at(Y, 6), stock=10)
    snap(session, mat_offer, at(D, 7), stock=5)
    slope(session, lamp, D, 0.4)
    slope(session, fan, D, -0.2)
    slope(session, mat, D, None)  # insufficient signal
    slope(session, mat, D + timedelta(days=1), 2.0)
    return {"lamp": lamp, "fan": fan, "mat": mat, "old": old}


def statuses(body: Any) -> dict[str, str]:
    return {name: section["status"] for name, section in body["sections"].items()}


@pytest.mark.db
def test_without_shopify_the_cj_trends_and_scores_sections_are_populated(
    api: TestClient, db_engine: Engine
) -> None:
    """WF-6's verify: with the Shopify source disabled, at least three sections are ok."""
    with Session(db_engine) as session:
        workspace_id = workspace(session, **FEES)
        ids = market(session)
        session.commit()
    body = get(api, workspace_id, date=D.isoformat())
    found = statuses(body)
    assert [name for name, status in found.items() if status == "ok"] == [
        "emerging", "movers_up", "movers_down", "suppliers", "search",
    ]  # fmt: skip
    new = body["sections"]["new_in_stores"]
    assert (new["status"], new["reason"], new["items"]) == (
        "no_source", "The Shopify store crawler is off.", [],
    )  # fmt: skip
    margins = body["sections"]["margins"]
    assert margins["status"] == "no_source"  # no store price: a margin needs a market price
    assert body["day"] == D.isoformat()
    assert body["cutoff"] == f"{(D + timedelta(days=1)).isoformat()}T00:00:00Z"

    search = body["sections"]["search"]
    assert [(i["product"]["id"], i["slope"], i["change_pct"]) for i in search["items"]] == [
        (str(ids["lamp"]), 0.4, 49.2), (str(ids["fan"]), -0.2, -18.1),
    ]  # fmt: skip
    assert search["as_of"] == f"{(D - timedelta(days=2)).isoformat()}T09:00:00Z"
    suppliers = body["sections"]["suppliers"]["items"]
    stock, price = suppliers  # stock flips first
    assert (stock["was_in_stock"], stock["in_stock"], stock["price_change_pct"]) == (
        True, False, None,
    )  # fmt: skip
    assert stock["as_of"] == f"{D.isoformat()}T07:00:00Z"
    assert (price["old_price_minor"], price["new_price_minor"], price["price_change_pct"]) == (
        740, 690, -6.8,
    )  # fmt: skip
    assert (price["product"]["id"], price["source"], price["in_stock"]) == (
        str(ids["lamp"]), "cj", None,
    )  # fmt: skip


@pytest.mark.db
def test_nothing_captured_after_the_cutoff_reaches_the_day(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **FEES)
        ids = market(session)
        alert(session, workspace_id, at(D, 8))
        alert(session, workspace_id, AFTER)
        alert(session, workspace_id, at(Y, 23))
        session.commit()
    body = get(api, workspace_id, date=D.isoformat())
    sections = body["sections"]
    mat = next(i for i in sections["emerging"]["items"] if i["product"]["id"] == str(ids["mat"]))
    assert (mat["value"], mat["stage"], mat["since_yesterday"]) == (64.0, "emerging", None)
    assert all(i["product"]["id"] != str(ids["mat"]) for i in sections["search"]["items"])
    prices = [i["new_price_minor"] for i in sections["suppliers"]["items"]]
    assert 999 not in prices and prices.count(690) == 1
    stocks = [i["in_stock"] for i in sections["suppliers"]["items"]]
    assert stocks.count(False) == 1  # the restock after the cutoff isn't read
    assert [a["fired_at"] for a in sections["alerts"]["items"]] == [f"{D.isoformat()}T08:00:00Z"]
    for section in sections.values():
        assert section["as_of"] is None or section["as_of"] <= body["cutoff"]

    # The next day sees them: D + 1's own rows, its alert, and the restock.
    later = get(api, workspace_id, date=(D + timedelta(days=1)).isoformat())["sections"]
    assert later["emerging"]["items"][0]["value"] == 99.0
    assert [i["in_stock"] for i in later["suppliers"]["items"]] == [True, None]
    assert len(later["alerts"]["items"]) == 1


@pytest.mark.db
def test_movers_carry_old_new_and_a_signed_change_and_never_overlap(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session)
        ids = market(session)
        session.commit()
    body = get(api, workspace_id)  # the newest scored day: D + 1, when only Mat scored
    assert body["day"] == (D + timedelta(days=1)).isoformat()
    [mat] = body["sections"]["movers_up"]["items"]
    assert (mat["product"]["id"], mat["change"]) == (str(ids["mat"]), 35.0)
    sections = get(api, workspace_id, date=D.isoformat())["sections"]
    up, down = sections["movers_up"]["items"], sections["movers_down"]["items"]
    assert [(i["product"]["id"], i["old"], i["new"], i["change"]) for i in up] == [
        (str(ids["lamp"]), 60.0, 71.0, 11.0)
    ]
    assert [(i["product"]["id"], i["old"], i["new"], i["change"]) for i in down] == [
        (str(ids["fan"]), 50.0, 42.0, -8.0)
    ]
    assert {i["product"]["id"] for i in up}.isdisjoint(i["product"]["id"] for i in down)
    assert all(i["model_version"] == V1 for i in up + down)  # "Old version" changed version
    emerging = sections["emerging"]["items"]
    assert [(i["product"]["id"], i["stage"]) for i in emerging] == [
        (str(ids["lamp"]), "rising"), (str(ids["mat"]), "emerging"),
    ]  # fmt: skip
    assert emerging[0]["since_yesterday"]["change"] == 11.0
    assert sections["emerging"]["sources"] == ["trend", "lifecycle"]
    assert sections["emerging"]["as_of"] == f"{(D + timedelta(days=1)).isoformat()}T00:00:00Z"


def lamp(session: Session) -> tuple[UUID, int]:
    """$29.99 in a store (a CSV import, say: Shopify stays disabled), $7.40 at CJ on Y and $6.90
    on D, $4.10 to the US; a freight quote after D's cutoff."""
    product_id = product(session, "Sunset lamp")
    store, cj = offer(session, product_id, SHOPIFY), offer(session, product_id)
    snap(session, store, at(Y, 6), price_min_minor=2999)
    snap(session, cj, at(Y, 6), price_min_minor=740)
    snap(session, cj, at(D, 6), price_min_minor=690)
    for captured, cost in ((at(Y, 6), 410), (AFTER, 9999)):
        observe(
            session, ShippingOption, CJ, captured, listing_id=cj, destination_country="US",
            quantity=1, method="CJPacket", cost_minor=cost, currency="USD",
        )  # fmt: skip
    return product_id, cj


def margin_bps(settings: WorkspaceSettings, unit: int) -> int:
    calc = landed_cost(
        Inputs(
            price_minor=2999, unit_cost=Amount(unit, "USD"), freight=Amount(410, "USD"),
            duty_bps=0, customs_fee_minor=settings.customs_fee_minor,
            payment_fee_bps=settings.payment_fee_bps,
            payment_fee_fixed_minor=settings.payment_fee_fixed_minor,
            shopify_fee_bps=settings.shopify_fee_bps, returns_bps=settings.returns_bps,
        )
    )  # fmt: skip
    assert calc.margin_bps is not None
    return calc.margin_bps


@pytest.mark.db
def test_each_workspace_reads_only_its_alerts_watchlists_and_margins(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        dutied = workspace(session, **FEES, duty_default_bps=0)
        undutied = workspace(session, **(FEES | {"payment_fee_bps": 600}))  # duty not set
        bare = workspace(session)  # no settings
        product_id, cj = lamp(session)
        other = product(session, "Other")
        merged = product(session, "Merged", merged_into_id=product_id)
        unread = alert(session, dutied, at(D, 8), entity_id=str(cj))
        read = alert(session, dutied, at(D, 9), read_at=at(D, 10))
        alert(session, undutied, at(D, 8), type="back_in_stock")
        watch(session, dutied, "Main", product_id, merged)
        watch(session, undutied, "Ideas", other)
        score(session, product_id, "trend", Y, 40.0)
        score(session, product_id, "trend", D, 45.5)
        score(session, product_id, "trend", D - timedelta(days=20), 10.0)  # outside 14 days
        score(session, product_id, "lifecycle", Y, stage="emerging")
        score(session, product_id, "lifecycle", D, stage="rising")
        session.commit()
        settings = session.get_one(WorkspaceSettings, dutied)
        expected = (margin_bps(settings, 740), margin_bps(settings, 690))

    a = get(api, dutied, date=D.isoformat())["sections"]
    assert [i["id"] for i in a["alerts"]["items"]] == [unread, read]  # unread first
    assert a["alerts"]["unread"] == 1
    [main] = a["watchlists"]["items"]
    assert (main["name"], main["item_count"]) == ("Main", 2)
    [item] = main["items"]  # the merged product reads as its survivor, once
    assert item["product"]["id"] == str(product_id)
    assert item["trend"] == {
        "old": 40.0, "new": 45.5, "change": 5.5,
        "as_of": f"{(D + timedelta(days=1)).isoformat()}T00:00:00Z",
    }  # fmt: skip
    assert (item["stage_before"], item["stage"]) == ("emerging", "rising")
    assert item["alerts"] == ["supplier_price_change"]
    assert [(p["day"], p["value"]) for p in item["series"]] == [
        (Y.isoformat(), 40.0), (D.isoformat(), 45.5),
    ]  # fmt: skip
    [moved] = a["margins"]["items"]
    assert (moved["old_bps"], moved["new_bps"]) == expected  # the D + 1 freight quote unread
    assert moved["change_bps"] == expected[1] - expected[0] > 0
    assert (moved["duty_not_set"], moved["supplier_listing_id"]) == (False, cj)
    assert moved["as_of"] == f"{Y.isoformat()}T06:00:00Z"  # its oldest input

    b = get(api, undutied, date=D.isoformat())["sections"]
    assert [i["type"] for i in b["alerts"]["items"]] == ["back_in_stock"]
    assert [w["name"] for w in b["watchlists"]["items"]] == ["Ideas"]
    assert b["watchlists"]["items"][0]["items"][0]["alerts"] == []
    [costed] = b["margins"]["items"]  # costed at duty 0, as Opportunity reads it
    assert costed["duty_not_set"] is True and costed["new_bps"] < moved["new_bps"]

    c = get(api, bare, date=D.isoformat())["sections"]
    assert (c["margins"]["status"], c["margins"]["reason"]) == (
        "no_source", "No workspace settings yet.",
    )  # fmt: skip
    assert (c["alerts"]["status"], c["watchlists"]["status"]) == ("empty", "empty")


@pytest.mark.db
def test_the_dated_view_at_a_late_cutoff_is_the_live_view(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **FEES, duty_default_bps=0)
        product_id, _ = lamp(session)
        session.commit()
        view = workspace_product_economics.c
        live = session.execute(
            select(workspace_product_economics).where(view.workspace_id == workspace_id)
        ).mappings().one()  # fmt: skip
        dated = pulse.economics(session, workspace_id, [product_id], AFTER + timedelta(days=1))
        assert dict(dated[product_id]) == dict(live)
        before = pulse.economics(session, workspace_id, [product_id], at(D, 0))
        assert before[product_id]["goods_minor"] == 740 and live["goods_minor"] == 690
        assert live["freight_minor"] == 9999  # the live view reads the late quote...
        assert before[product_id]["freight_minor"] == 410  # ...the dated one doesn't


@pytest.mark.db
def test_the_dated_view_is_the_live_view_text_but_for_the_cutoff_rewrites(
    db_engine: Engine,
) -> None:
    """XR-67: a view migration Pulse misses fails here, ORDER BY (the pick) first."""
    dated = pulse.dated_economics()
    for table in ("listing_snapshots", "shipping_options"):
        dated = dated.replace(f"(SELECT * FROM {table} WHERE captured_at < :cutoff)", table)
    dated = re.sub(r"\((\w+)\.delisted_at IS NULL OR \1\.delisted_at >= :cutoff\)",
                   r"\1.delisted_at IS NULL", dated)  # fmt: skip
    dated = dated.replace(" AND s.workspace_id = :workspace_id AND p.id IN :ids", "")
    assert not re.search(r":(cutoff|workspace_id|ids)\b", dated)  # every rewrite undone
    with db_engine.begin() as connection:
        connection.execute(text(f"CREATE TEMP VIEW dated AS {dated}"))
        live, undone = (
            connection.scalar(text("SELECT pg_get_viewdef(CAST(:view AS regclass), true)"),
                              {"view": view})
            for view in ("workspace_product_economics", "dated")
        )  # fmt: skip
    assert re.findall(r"ORDER BY .*", undone) == re.findall(r"ORDER BY .*", live)
    assert undone == live


@pytest.mark.db
def test_with_duty_unset_the_margin_costs_the_live_views_cheapest_listing(
    api: TestClient, db_engine: Engine
) -> None:
    """XR-67's probe: $29.99 in a store and two CJ listings with $4.10 freight, $20.00 (created
    first, the lower id) and $5.00, one of which goes up $1 on D. Duty unset, every listing is
    incomplete and both views cost the cheapest (DEC-341), not the lowest id."""
    with Session(db_engine) as session:
        workspace_id = workspace(session, **FEES)  # duty not set
        cheap_moves, dear_moves = product(session, "Cheap one moves"), product(session, "Dear")
        cheap: dict[UUID, int] = {}
        for product_id, moving in ((cheap_moves, 500), (dear_moves, 2000)):
            snap(session, offer(session, product_id, SHOPIFY), at(Y, 6), price_min_minor=2999)
            for unit in (2000, 500):
                cheap[product_id] = cj = offer(session, product_id)
                snap(session, cj, at(Y, 6), price_min_minor=unit)
                if unit == moving:
                    snap(session, cj, at(D, 6), price_min_minor=unit + 100)
                observe(
                    session, ShippingOption, CJ, at(Y, 6), listing_id=cj,
                    destination_country="US", quantity=1, method="CJPacket", cost_minor=410,
                    currency="USD",
                )  # fmt: skip
        session.commit()
        view = workspace_product_economics.c
        live = session.execute(
            select(view.product_id, view.supplier_listing_id).where(
                view.workspace_id == workspace_id
            )
        ).tuples()  # fmt: skip
        assert dict(live.all()) == cheap

    margins = get(api, workspace_id, date=D.isoformat())["sections"]["margins"]
    [moved] = margins["items"]  # the dear listing's move is not the margin's
    assert moved["product"]["id"] == str(cheap_moves)
    assert (moved["old_bps"], moved["new_bps"]) == (6075, 5742)
    assert (moved["supplier_listing_id"], moved["duty_not_set"]) == (cheap[cheap_moves], True)


@pytest.mark.db
def test_an_empty_database_answers_every_section_empty_or_no_source(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session)
        session.commit()
        assert session.scalar(text("SELECT count(*) FROM scores")) == 0
    body = get(api, workspace_id)
    assert body["day"] == (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    assert set(statuses(body).values()) <= {"empty", "no_source"}
    for section in body["sections"].values():
        assert (section["items"], section["as_of"]) == ([], None)
        assert section["reason"]
    assert statuses(body)["emerging"] == "no_source"


@pytest.mark.db
def test_launches_list_tracked_stores_new_listings_but_not_their_back_catalogue(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        tracking, other = workspace(session), workspace(session)
        session.execute(text("UPDATE sources SET enabled = true WHERE key = 'shopify_stores'"))
        stores = [Store(domain=f"s{i}.example.test", platform="shopify") for i in range(2)]
        session.add_all(stores)
        session.flush()
        session.add(WorkspaceTrackedStore(workspace_id=tracking, store_id=stores[0].id))
        for store, published, title in (
            (stores[0], at(Y, 12), "Launch"),
            (stores[0], at(D - timedelta(days=200), 0), "Back catalogue"),
            (stores[1], at(Y, 12), "Untracked store"),
        ):
            session.add(
                Listing(
                    source_id=SHOPIFY, external_id=uuid4().hex, url="https://example.test/p",
                    title=title, store_id=store.id, first_seen_at=at(D, 3),
                    source_published_at=published,
                )
            )  # fmt: skip
        session.commit()
    new = get(api, tracking, date=D.isoformat())["sections"]["new_in_stores"]
    assert [(i["title"], i["store"], i["product"]) for i in new["items"]] == [
        ("Launch", "s0.example.test", None)
    ]
    assert (new["status"], new["as_of"]) == ("ok", f"{D.isoformat()}T03:00:00Z")
    quiet = get(api, other, date=D.isoformat())["sections"]["new_in_stores"]
    assert (quiet["status"], quiet["reason"]) == ("no_source", "No tracked stores yet.")
    later = get(api, tracking, date=(D + timedelta(days=1)).isoformat())["sections"]
    assert later["new_in_stores"]["status"] == "empty"
