"""Testing Board API (WF-5 part a, R-21, R-24, DEC-312): workspace product tests with computed
CPA and ROAS, a start snapshot taken once, and kill-reason counts."""

import csv
import io
from collections.abc import Callable, Iterator
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any, get_args
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.csv_export import major
from pulso_api.dependencies import get_db
from pulso_api.routers.testing import NO_BREAK_EVEN, TESTING_CSV, KillReason, Stage, stop_loss
from pulso_core.db import Base
from pulso_core.landed_cost import Amount, Inputs, landed_cost
from pulso_core.models import (
    CollectorRun,
    Image,
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


# The vault's worked example through the one landed-cost function: $39.99, $14.20 landed,
# 2.9% + $0.30 = $1.46 fees, so break-even CPA $24.33 and a $48.66 stop-loss.
EXAMPLE = asdict(
    landed_cost(
        Inputs(price_minor=3999, unit_cost=Amount(1420, "USD"), freight=Amount(0, "USD"),
               duty_bps=0, payment_fee_bps=290, payment_fee_fixed_minor=30)
    )
)  # fmt: skip


def signal(spend: int, orders: int, snapshot: dict[str, Any] | None = EXAMPLE) -> Any:
    cpa = round(Fraction(spend, orders)) if orders else None
    return stop_loss("testing", snapshot, spend, orders, cpa)["signal"]


def test_the_worked_example_to_the_cent() -> None:
    assert pick(EXAMPLE, "landed_cost_minor", "payment_fee_minor", "margin_minor") == (
        1420, 146, 2433
    )  # fmt: skip
    economics = stop_loss("testing", EXAMPLE, 0, 0, None)
    assert economics == {"break_even_cpa_minor": 2433, "stop_loss_minor": 4866, "signal": None,
                         "signal_reason": None}  # fmt: skip
    assert (signal(4865, 0), signal(4866, 0)) == (None, "over_stop_loss")  # $48.66


@pytest.mark.parametrize(
    ("spend", "orders", "expected"),
    [(4865, 0, None), (4866, 0, "over_stop_loss"), (10**6, 1, None),
     (4 * 2434, 4, None), (4 * 2433, 4, None),  # N - 1 orders: no call either way
     (5 * 2433, 5, "winner_candidate"), (5 * 2433 + 2, 5, "winner_candidate"),  # $24.334
     (5 * 2433 + 3, 5, "over_stop_loss"), (5 * 2434, 5, "over_stop_loss"),  # $24.336, $24.34
     (0, 5, "winner_candidate"), (2433 * 7, 7, "winner_candidate")],
)  # fmt: skip
def test_the_stop_loss_and_winner_boundaries(spend: int, orders: int, expected: Any) -> None:
    assert signal(spend, orders) == expected


def test_no_break_even_no_signal() -> None:
    incomplete = landed_cost(Inputs(price_minor=None, unit_cost=None, freight=None, duty_bps=0))
    economics = stop_loss("testing", asdict(incomplete), 10**6, 0, None)
    assert economics == {"break_even_cpa_minor": None, "stop_loss_minor": None, "signal": None,
                         "signal_reason": NO_BREAK_EVEN}  # fmt: skip
    assert NO_BREAK_EVEN == "Set price and supplier to compute break-even."
    # Only Testing gets a signal or a reason; before a snapshot there is none.
    assert stop_loss("killed", EXAMPLE, 10**6, 0, None)["signal"] is None
    assert stop_loss("idea", None, 0, 0, None)["signal_reason"] is None
    # A break-even at or below zero: every spend is past it, and no budget is suggested.
    loss = EXAMPLE | {"margin_minor": -150}
    assert pick(stop_loss("testing", loss, 0, 0, None), "stop_loss_minor", "signal") == (
        None, "over_stop_loss"
    )  # fmt: skip


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
    return {"listing": cj.id, "variant": variant.id, "quote": quote.id, "shop": shop.id}


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
def test_changed_since_start_compares_a_fresh_calc_and_keeps_the_snapshot(
    board: tuple[As, dict[str, Any]], db_engine: Engine
) -> None:
    as_, ids = board
    api = as_("a")
    url = f"/v1/tests/{create(api, ids['p0'])['id']}"
    assert api.get(url).json()["since_start"] is None  # no snapshot yet
    scenario = {"supplier_listing_id": ids["listing"], "variant_id": ids["variant"],
                "ad_cost_minor": 1800}  # fmt: skip
    test = api.patch(url, json={"stage": "testing", "scenario": scenario}).json()
    economics = pick(test, "break_even_cpa_minor", "stop_loss_minor", "signal", "signal_reason")
    assert economics == (2253, 4506, None, None)  # $22.53 break-even, 2 x = $45.06
    assert api.get(url).json()["since_start"] == {"changes": [], "reason": None,
                                                  "as_of": "2026-10-23T12:00:00Z"}  # fmt: skip
    # Five orders at $22.54 each are past break-even; at $22.53 a winner candidate.
    assert api.patch(url, json={"ad_spend_minor": 11270, "orders": 5}).json()["signal"] == (
        "over_stop_loss"
    )  # fmt: skip
    assert api.patch(url, json={"ad_spend_minor": 11265}).json()["signal"] == "winner_candidate"
    snap = test["start_snapshot"]
    with Session(db_engine) as session:
        stored = session.get(ProductTest, test["id"])
        assert stored is not None and stored.start_snapshot == snap

    # A new freight quote and a new duty rate; the test's price and the owner's CPA estimate stay
    # the scenario's, whatever the store price and the default CPA do.
    with Session(db_engine) as session:
        observe(session, ListingSnapshot, SHOPIFY, DAY + timedelta(days=1), listing_id=ids["shop"],
                values_hash="h2", currency="USD", price_min_minor=4499)  # fmt: skip
        quote = observe(session, ShippingOption, CJ, DAY + timedelta(days=1),
                        listing_id=ids["listing"], variant_id=ids["variant"],
                        destination_country="US", quantity=1, method="CJPacket", cost_minor=500,
                        currency="USD")  # fmt: skip
        session.commit()
        new_quote = quote.id
    patch = {"duty_default_bps": 2500, "default_cpa_minor": 999}
    assert api.patch("/v1/settings", json=patch).status_code == 200
    body = api.get(url).json()
    # $39.99 - ($10.00 + $5.00 + 25% duty $2.50) - $1.46 fees = $21.03
    assert body["since_start"]["changes"] == [
        {"input": "freight_quote_id", "old": ids["quote"], "new": new_quote},
        {"input": "freight_minor", "old": 400, "new": 500},
        {"input": "duty_bps", "old": 2000, "new": 2500},
        {"input": "margin_minor", "old": 2253, "new": 2103},
    ]
    assert body["start_snapshot"] == snap and body["break_even_cpa_minor"] == 2253
    with Session(db_engine) as session:
        stored = session.get(ProductTest, test["id"])
        assert stored is not None and stored.start_snapshot == snap

    # A fresh calc that can't run says why, never a blank.
    with Session(db_engine) as session:
        session.execute(update(Listing).where(Listing.id == ids["listing"]).values(delisted_at=DAY))
        session.commit()
    assert api.get(url).json()["since_start"] == {
        "changes": [], "reason": "Supplier listing not found on this product.", "as_of": None
    }  # fmt: skip
    # An incomplete snapshot: no break-even, no signal, and the reason.
    other = create(api, ids["p1"], stage="testing", ad_spend_minor=10**6)
    assert pick(other, "break_even_cpa_minor", "signal", "signal_reason") == (
        None, None, NO_BREAK_EVEN
    )  # fmt: skip


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
def test_tests_carry_their_product_title_and_image_in_one_query(
    board: tuple[As, dict[str, Any]], db_engine: Engine
) -> None:
    as_, ids = board
    with Session(db_engine) as session:  # p0's CJ listing gets the main image; p1 has none
        image = Image(listing_id=ids["listing"], url="https://cdn.test/lamp.jpg", position=0)
        session.add(image)
        session.flush()
        session.execute(
            update(Product).where(Product.id == ids["p0"]).values(main_image_id=image.id)
        )
        session.commit()
    api = as_("a")
    made = [create(api, ids[p]) for p in ("p0", "p1", "p2")]
    cards = [("Product 0", "https://cdn.test/lamp.jpg"), ("Product 1", None), ("Product 2", None)]
    assert [pick(test, "product_title", "product_image_url") for test in made] == cards
    statements: list[str] = []
    listen = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(db_engine, "before_cursor_execute", listen)
    try:
        items = api.get("/v1/tests").json()["items"]
    finally:
        event.remove(db_engine, "before_cursor_execute", listen)
    assert [pick(test, "product_title", "product_image_url") for test in items] == cards[::-1]
    assert len(statements) == 2  # the page with its products, then the kill-reason counts
    url = f"/v1/tests/{made[0]['id']}"
    for body in (api.get(url).json(), api.patch(url, json={"orders": 1}).json()):
        assert pick(body, "product_title", "product_image_url") == cards[0]


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
    assert as_("a").get(url).json() == mine | {"since_start": None}


def export(api: TestClient, **query: Any) -> list[dict[str, str]]:
    """The Testing Board's CSV, checked for the format every export shares (DEC-316, DEC-345)."""
    response = api.get("/v1/tests", params={**query, "format": "csv"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="pulso_testing_{today()}.csv"'
    )
    assert response.content.startswith(b"\xef\xbb\xbf")  # the BOM, for Excel on Windows
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0] == ",".join(TESTING_CSV)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert response.headers["x-total-count"] == str(len(rows))
    return rows


@pytest.mark.db
def test_the_csv_export_is_the_jsons_tests_with_money_in_dollars(
    board: tuple[As, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("pulso_api.csv_export.CHUNK", 2)  # two fetches for three tests
    as_, ids = board
    api = as_("a")
    scenario = {"supplier_listing_id": ids["listing"], "variant_id": ids["variant"],
                "ad_cost_minor": 1800}  # fmt: skip
    # Five orders at $22.53 against the $22.53 break-even: a winner candidate.
    won = create(api, ids["p0"], stage="testing", scenario=scenario, ad_spend_minor=11265,
                 revenue_minor=25999, orders=5, notes="=HYPERLINK(1) lamp")  # fmt: skip
    idle = create(api, ids["p1"])  # no spend, no orders
    create(api, ids["p2"], stage="killed", kill_reason="saturated", ad_spend_minor=4865, orders=2)
    create(as_("b"), ids["p3"])  # another workspace's test never exports
    api = as_("a")

    page = api.get("/v1/tests").json()["items"]
    rows = export(api)
    assert [row["id"] for row in rows] == [str(test["id"]) for test in page]  # newest first
    row, item = rows[-1], page[-1]
    assert row == {
        "id": str(won["id"]),
        "product_id": ids["p0"],
        "product": "Product 0",
        "stage": "testing",
        "started_on": today(),
        "ended_on": "",
        "currency": "USD",
        "ad_spend": "112.65",
        "revenue": "259.99",
        "orders": "5",
        "cpa": "22.53",
        "roas": str(25999 / 11265),
        "break_even_cpa": "22.53",
        "stop_loss": "45.06",  # 2 x break-even
        "signal": "winner_candidate",
        "kill_reason": "",
        "notes": "'=HYPERLINK(1) lamp",  # the owner's text, still never a formula
        "created_at": item["created_at"],
        "updated_at": item["updated_at"],
    }
    # The computed values are the JSON's, read through the same view, never re-derived.
    assert (row["cpa"], row["roas"], row["break_even_cpa"], row["stop_loss"]) == (
        str(major(item["cpa_minor"])), str(item["roas"]),
        str(major(item["break_even_cpa_minor"])), str(major(item["stop_loss_minor"])),
    )  # fmt: skip
    assert row["created_at"].endswith("Z") and row["updated_at"].endswith("Z")
    # No spend and no orders: CPA, ROAS and break-even are empty cells, never 0 (DEC-040).
    blank = next(r for r in rows if r["id"] == str(idle["id"]))
    assert pick(blank, "ad_spend", "orders", "cpa", "roas", "break_even_cpa", "signal") == (
        "0.00", "0", "", "", "", ""
    )  # fmt: skip

    killed = export(api, stage="killed")  # the list's filter; a cursor and limit are the page's
    assert [pick(r, "stage", "kill_reason", "cpa") for r in killed] == [
        ("killed", "saturated", "24.32")  # $48.65 / 2, half-even as the card shows
    ]
    assert len(export(api, cursor=page[0]["id"], limit=1)) == 3
    assert [r["product"] for r in export(as_("b"))] == ["Product 3"]


@pytest.mark.db
def test_the_csv_export_over_the_cap_is_a_422_and_no_file(
    board: tuple[As, dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    as_, ids = board
    api = as_("a")
    for product in ("p1", "p2"):
        create(api, ids[product])
    create(api, ids["p3"], stage="killed", kill_reason="other")
    monkeypatch.setattr("pulso_api.csv_export.MAX_ROWS", 2)
    response = api.get("/v1/tests", params={"format": "csv"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert (response.json()["code"], response.json()["detail"]) == (
        "export_too_large",
        "3 rows exceed the 2 export limit. Narrow your filters.",
    )
    assert len(export(api, stage="idea")) == 2  # narrowed under the cap, it exports
    assert api.get("/v1/tests", params={"format": "xlsx"}).status_code == 422
