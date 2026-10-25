"""Testing Board API (WF-5 part a, R-21, R-24, DEC-312): workspace product tests with computed
CPA and ROAS, a start snapshot taken once, and kill-reason counts."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, get_args
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.testing import KillReason, Stage
from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    ListingVariant,
    Product,
    ProductTest,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    User,
    VariantSnapshot,
    Workspace,
    WorkspaceSettings,
)
from pulso_core.models.core import KILL_REASONS, TEST_STAGES

As = Callable[[str], TestClient]
SHOPIFY, CJ = 1, 2  # seeded source ids
DAY = datetime(2026, 10, 23, 12, tzinfo=UTC)


def test_tests_require_a_session(client: TestClient) -> None:
    assert client.get("/v1/tests").status_code == 401


def test_cpa_and_roas_are_never_stored() -> None:
    assert not {"cpa", "cpa_minor", "roas"} & set(ProductTest.__table__.c.keys())


def test_the_api_literals_match_the_table_checks() -> None:
    assert (get_args(Stage), get_args(KillReason)) == (TEST_STAGES, KILL_REASONS)


@pytest.mark.parametrize(
    "field",
    [{"stage": "paused"}, {"stage": None}, {"ad_spend_minor": -1}, {"revenue_minor": 2**63},
     {"orders": -1}, {"orders": "3"}, {"notes": "b\x00d"}, {"kill_reason": "bored"},
     {"currency": "EUR"}, {"cpa_minor": 100}, {"start_snapshot": {}},
     {"scenario": {"quantity": 0}}],
)  # fmt: skip
def test_create_validates_fields(client: TestClient, field: dict[str, Any]) -> None:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    response = client.post("/v1/tests", json={"product_id": str(uuid4()), **field})
    assert response.status_code == 422, response.text


def observe[T: Base](
    session: Session, model: type[T], source_id: int, at: datetime = DAY, **values: Any
) -> T:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id, run_id=run.id, captured_at=at, request={}, bytes=1, sha256="0" * 64
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=at, observed_for=at.date(), raw_payload_id=payload.id, **values)
    session.add(row)
    session.flush()
    return row


def priced(session: Session, product: Product) -> dict[str, int]:
    """A $39.99 store price, and a CJ variant at $10.00 with a $4.00 US freight quote."""
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add_all([store, supplier])
    session.flush()
    listing = {"url": "https://x.test/p", "title": "Lamp", "product_id": product.id}
    shop = Listing(source_id=SHOPIFY, external_id="shop", store_id=store.id, **listing)
    cj = Listing(source_id=CJ, external_id=uuid4().hex, supplier_id=supplier.id, **listing)
    session.add_all([shop, cj])
    session.flush()
    variant = ListingVariant(listing_id=cj.id, external_id="v1")
    session.add(variant)
    session.flush()
    observe(session, ListingSnapshot, SHOPIFY, listing_id=shop.id, values_hash="h",
            currency="USD", price_min_minor=3999)  # fmt: skip
    observe(session, VariantSnapshot, CJ, variant_id=variant.id, values_hash="h",
            currency="USD", price_minor=1000)  # fmt: skip
    quote = observe(session, ShippingOption, CJ, listing_id=cj.id, variant_id=variant.id,
                    destination_country="US", quantity=1, method="CJPacket", cost_minor=400,
                    currency="USD")  # fmt: skip
    return {"listing": cj.id, "variant": variant.id, "quote": quote.id}


@pytest.fixture
def board(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, Any]]:
    """`as_("a")` makes the next requests workspace A's; ids holds the products and economics."""
    with Session(db_engine) as session:
        users = {key: User(clerk_user_id=f"user_{key}") for key in "ab"}
        workspaces = {key: Workspace(name=f"Workspace {key}") for key in "ab"}
        products = [Product(name=f"Product {n}") for n in range(4)]
        session.add_all([*users.values(), *workspaces.values(), *products])
        session.flush()
        fees = {"duty_default_bps": 2000, "payment_fee_bps": 290, "payment_fee_fixed_minor": 30}
        session.add(WorkspaceSettings(workspace_id=workspaces["a"].id, **fees))
        ids: dict[str, Any] = priced(session, products[0])
        session.commit()
        ids |= {f"p{n}": str(product.id) for n, product in enumerate(products)}
        principals = {key: Principal(users[key].id, workspaces[key].id) for key in "ab"}

    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    app = client.app
    app.dependency_overrides[get_db] = database

    def as_(key: str) -> TestClient:
        app.dependency_overrides[current_principal] = lambda: principals[key]
        return client

    return as_, ids


def create(api: TestClient, product: str, **body: Any) -> Any:
    response = api.post("/v1/tests", json={"product_id": product, **body})
    assert response.status_code == 201, response.text
    return response.json()


def pick(body: dict[str, Any], *keys: str) -> tuple[Any, ...]:
    return tuple(body[key] for key in keys)


def problem(response: Any) -> tuple[int, str]:
    return response.status_code, response.json()["code"]


def today() -> str:
    return datetime.now(UTC).date().isoformat()


@pytest.mark.db
def test_cpa_and_roas_match_a_hand_calculation(board: tuple[As, dict[str, Any]]) -> None:
    as_, ids = board
    api = as_("a")
    test = create(api, ids["p1"])
    assert pick(test, "stage", "currency", "cpa_minor", "roas") == ("idea", "USD", None, None)
    url = f"/v1/tests/{test['id']}"

    def metrics(**patch: int) -> tuple[Any, ...]:
        return pick(api.patch(url, json=patch).json(), "cpa_minor", "roas")

    # $200.00 / 3 orders = $66.667 → $66.67; $259.99 / $200.00 = 1.29995
    assert metrics(ad_spend_minor=20000, revenue_minor=25999, orders=3) == (6667, 1.29995)
    # $48.65 / 2 = $24.325: half-even keeps $24.32 where half-up would say $24.33
    assert metrics(ad_spend_minor=4865, orders=2) == (2432, 25999 / 4865)
    assert metrics(orders=0) == (None, 25999 / 4865)
    assert metrics(ad_spend_minor=0, orders=1) == (0, None)
    assert pick(api.get(url).json(), "cpa_minor", "roas") == (0, None)


@pytest.mark.db
def test_killed_needs_a_kill_reason(board: tuple[As, dict[str, Any]]) -> None:
    as_, ids = board
    api = as_("a")
    url = f"/v1/tests/{create(api, ids['p1'])['id']}"
    for patch in ({"stage": "killed"}, {"kill_reason": "saturated"}):
        assert problem(api.patch(url, json=patch)) == (422, "kill_reason"), patch
    assert api.get(url).json()["stage"] == "idea"  # nothing saved
    body = api.patch(url, json={"stage": "killed", "kill_reason": "saturated"}).json()
    assert pick(body, "stage", "kill_reason", "ended_on") == ("killed", "saturated", today())
    assert api.patch(url, json={"kill_reason": None}).status_code == 422
    assert api.patch(url, json={"kill_reason": "other"}).json()["kill_reason"] == "other"
    body = api.patch(url, json={"stage": "researching"}).json()  # reopened: reason and end clear
    assert pick(body, "stage", "kill_reason", "ended_on") == ("researching", None, None)
    response = api.post("/v1/tests", json={"product_id": ids["p2"], "stage": "killed"})
    assert problem(response) == (422, "kill_reason")
    response = api.patch(url, json={"started_on": "2026-10-20", "ended_on": "2026-10-19"})
    assert problem(response) == (422, "date_order")


@pytest.mark.db
def test_entering_testing_snapshots_the_profit_calc_once(
    board: tuple[As, dict[str, Any]], db_engine: Engine
) -> None:
    as_, ids = board
    api = as_("a")
    test = create(api, ids["p0"], notes="Sunset lamp")
    assert pick(test, "start_snapshot", "started_on", "notes") == (None, None, "Sunset lamp")
    url = f"/v1/tests/{test['id']}"
    scenario = {"supplier_listing_id": ids["listing"], "variant_id": ids["variant"]}
    body = api.patch(url, json={"stage": "testing", "scenario": scenario | {"ad_cost_minor": 1800}})
    assert (body.status_code, body.json()["started_on"]) == (200, today()), body.text
    snap = body.json()["start_snapshot"]
    chosen = pick(snap, "supplier_listing_id", "variant_id", "freight_quote_id")
    assert chosen == pick(ids, "listing", "variant", "quote")
    rates = pick(snap, "duty_bps", "payment_fee_bps", "payment_fee_fixed_minor", "ad_cost_minor")
    assert (rates, snap["estimates"]) == ((2000, 290, 30, 1800), ["ad_cost_minor"])
    # $39.99 - ($10.00 + $4.00 freight + 20% duty $2.00) - (2.9% $1.16 + $0.30) = $22.53
    economics = pick(snap, "price_minor", "landed_cost_minor", "margin_minor", "complete")
    assert economics == (3999, 1600, 2253, True) and snap["captured_at"]

    # A fee, the supplier's price, metrics and a stage round trip leave it as it was.
    assert api.patch("/v1/settings", json={"payment_fee_bps": 500}).status_code == 200
    with Session(db_engine) as session:
        observe(session, VariantSnapshot, CJ, DAY + timedelta(days=1), variant_id=ids["variant"],
                values_hash="h2", currency="USD", price_minor=2000)  # fmt: skip
        session.commit()
    for patch in (
        {"ad_spend_minor": 5000, "orders": 1},
        {"stage": "researching"},
        {"stage": "testing"},
    ):
        assert api.patch(url, json=patch).json()["start_snapshot"] == snap, patch  # fmt: skip
    assert api.patch(url, json={"start_snapshot": {}}).status_code == 422
    assert problem(api.patch(url, json={"scenario": scenario})) == (422, "snapshot_locked")
    with Session(db_engine) as session, pytest.raises(DBAPIError, match="immutable"):
        session.execute(update(ProductTest).values(start_snapshot={}))
    assert api.get(url).json()["start_snapshot"] == snap

    # Without a scenario, the default one; missing inputs stay named, never guessed.
    snap = create(api, ids["p1"], stage="testing")["start_snapshot"]
    assert pick(snap, "complete", "supplier_listing_id", "margin_minor") == (False, None, None)
    assert "price_missing" in snap["missing"]


@pytest.mark.db
def test_list_pages_filters_and_counts_kill_reasons(board: tuple[As, dict[str, Any]]) -> None:
    as_, ids = board
    api = as_("a")
    killed = [("p1", "saturated"), ("p2", "saturated"), ("p3", "other")]
    created = [create(api, ids[p], stage="killed", kill_reason=why)["id"] for p, why in killed]
    created += [create(api, ids["p3"])["id"], create(api, ids["p1"], stage="winner")["id"]]
    counts = {"saturated": 2, "other": 1}
    seen, cursor = [], None
    while True:
        page = api.get("/v1/tests", params={"limit": 2} | ({"cursor": cursor} if cursor else {}))
        seen += [item["id"] for item in page.json()["items"]]
        assert page.json()["kill_reasons"] == counts
        if (cursor := page.json()["next_cursor"]) is None:
            break
    assert seen == created[::-1]  # newest first, each once
    page = api.get("/v1/tests", params={"stage": "killed", "limit": 1}).json()
    assert ([item["id"] for item in page["items"]], page["kill_reasons"]) == ([created[2]], counts)
    # One open test per product: p3 already has one.
    assert problem(api.post("/v1/tests", json={"product_id": ids["p3"]})) == (409, "conflict")
    for params in ({"cursor": "x"}, {"cursor": 0}, {"limit": 101}, {"stage": "paused"}):
        assert api.get("/v1/tests", params=params).status_code == 422, params
    assert api.get(f"/v1/tests/{2**62}").status_code == 404
    assert api.get(f"/v1/tests/{2**63}").status_code == 422
    assert api.post("/v1/tests", json={"product_id": str(uuid4())}).status_code == 404


@pytest.mark.db
def test_two_workspace_isolation(board: tuple[As, dict[str, Any]]) -> None:
    as_, ids = board
    mine = create(as_("a"), ids["p1"], stage="killed", kill_reason="other")
    url = f"/v1/tests/{mine['id']}"
    b = as_("b")
    assert b.get(url).status_code == 404
    assert b.patch(url, json={"notes": "mine now"}).status_code == 404
    assert b.get("/v1/tests").json() == {"items": [], "next_cursor": None, "kill_reasons": {}}
    theirs = create(b, ids["p1"])  # the open-test rule is per workspace
    assert [item["id"] for item in as_("a").get("/v1/tests").json()["items"]] == [mine["id"]]
    assert [item["id"] for item in as_("b").get("/v1/tests").json()["items"]] == [theirs["id"]]
    assert as_("a").get(url).json() == mine
