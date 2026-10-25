import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
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
from pulso_api.routers.product_scores import NO_ROW
from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    RawPayload,
    ShippingOption,
    Store,
    Supplier,
    Workspace,
    WorkspaceSettings,
    workspace_product_economics,
)
from pulso_core.scores import Explanation, Kind, ScoreRow, Stage, write
from pulso_ml.scores import opportunity

# SC-5 (DEC-331): stored Saturation, Trend and Lifecycle rows, and the caller's Opportunity,
# computed at read time from the workspace_product_economics view and never stored.
SHOPIFY, CJ = 1, 2  # seeded source ids
TODAY = datetime.now(UTC).date()
YESTERDAY = TODAY - timedelta(days=1)
LAMP_FEES = {"payment_fee_bps": 290, "payment_fee_fixed_minor": 30, "returns_bps": 500}


def test_scores_require_a_session(client: TestClient) -> None:
    assert client.get(f"/v1/products/{uuid4()}/scores").status_code == 401


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def scores(
    api: TestClient, workspace_id: UUID, product_id: UUID, status: int = 200, **q: Any
) -> Any:
    assert isinstance(api.app, FastAPI)
    api.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    response = api.get(f"/v1/products/{product_id}/scores", params=q, follow_redirects=False)
    assert response.status_code == status, response.text
    return response.json()


def observe[T: Base](session: Session, model: type[T], source_id: int, **values: Any) -> T:
    at = datetime.combine(YESTERDAY, datetime.min.time(), UTC) + timedelta(hours=6)
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id,
        run_id=run.id,
        captured_at=at,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=at, raw_payload_id=payload.id, observed_for=at.date(), **values)
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


def lamp(session: Session, costs: tuple[int, ...] = (740,)) -> UUID:
    """The note's worked example: $29.99 in a store, $7.40 at CJ, $4.10 to the US. `costs` are
    the CJ listings' prices in creation order, each with that quote."""
    product = Product(name="Sunset lamp")
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add_all([product, store, supplier])
    session.flush()
    for source, owner, price in (
        (SHOPIFY, {"store_id": store.id}, 2999),
        *((CJ, {"supplier_id": supplier.id}, cost) for cost in costs),
    ):
        listing = Listing(
            source_id=source, external_id=uuid4().hex, url="https://example.test/p",
            title="Sunset lamp", product_id=product.id, **owner,
        )  # fmt: skip
        session.add(listing)
        session.flush()
        observe(
            session, ListingSnapshot, source, listing_id=listing.id, values_hash="h",
            currency="USD", price_min_minor=price,
        )  # fmt: skip
        if source == CJ:
            observe(
                session, ShippingOption, CJ, listing_id=listing.id, destination_country="US",
                quantity=1, method="CJPacket", cost_minor=410, currency="USD",
            )  # fmt: skip
    return product.id


def score(
    session: Session,
    product_id: UUID,
    kind: Kind,
    value: float | None = None,
    day: date = YESTERDAY,
    stage: Stage | None = None,
    reason: str | None = None,
    model_version: str = "000-fixture00000",
) -> None:
    explanation = Explanation(
        model_version=model_version,
        config_digest="f" * 64,
        components=(),
        missing=(),
        coverage=0.0,
        reason=reason,
    )
    assert write(session, [ScoreRow(product_id, day, kind, value, explanation, stage)]) == 1


def scored_lamp(session: Session, costs: tuple[int, ...] = (740,)) -> UUID:
    product_id = lamp(session, costs)
    score(session, product_id, "trend", 68.6)
    score(session, product_id, "saturation", 73.3)
    score(session, product_id, "lifecycle", stage="rising", reason="growth over +20% a week")
    return product_id


def xmins(session: Session) -> list[tuple[int, str]]:
    return [
        tuple(row) for row in session.execute(text("SELECT id, xmin::text FROM scores ORDER BY id"))
    ]


@pytest.mark.db
def test_the_worked_example_scores_65_7_beta_with_duty_not_set(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **LAMP_FEES)
        product_id = scored_lamp(session)
        session.commit()
        view = workspace_product_economics.c
        lines = (view.price_minor, view.landed_cost_minor, view.payment_fee_minor)
        totals = (view.returns_minor, view.margin_minor, view.missing)
        row = session.execute(
            select(*lines, *totals).where(
                view.workspace_id == workspace_id, view.product_id == product_id
            )
        ).one()
        assert tuple(row) == (2999, None, 117, 150, None, ["duty_not_set"])  # R-16 withholds it

    body = scores(api, workspace_id, product_id)
    found = body["opportunity"]
    assert found["value"] == 65.7
    explanation = found["explanation"]
    trend, margin, room, risk = explanation["components"]
    assert (trend["name"], trend["source"], trend["z"]) == ("trend", "trend", 68.6)  # Beta
    assert (margin["raw"], margin["source"]) == (0.5275, opportunity.VIEW)  # $15.82 / $29.99
    assert room["z"] == pytest.approx(26.7)
    assert (risk["missing"], risk["source"]) == (True, None)
    assert explanation["missing"] == ["risk"]
    assert (explanation["confidence"], explanation["cautions"]) == (0.7, ["duty_not_set"])
    assert explanation["model_version"] == opportunity.VERSION
    assert found["as_of"] == f"{YESTERDAY.isoformat()}T06:00:00Z"  # the oldest input
    latest = body["latest"]
    assert (latest["trend"]["value"], latest["saturation"]["value"]) == (68.6, 73.3)
    assert (latest["lifecycle"]["value"], latest["lifecycle"]["stage"]) == (None, "rising")
    assert latest["lifecycle"]["explanation"]["reason"] == "growth over +20% a week"
    assert latest["trend"]["as_of"] <= f"{TODAY.isoformat()}T00:00:00Z"  # before the day's end
    assert sorted(r["kind"] for r in body["history"]) == ["lifecycle", "saturation", "trend"]


@pytest.mark.db
def test_a_fee_change_moves_opportunity_and_no_scores_row(
    api: TestClient, db_engine: Engine
) -> None:
    """The SC-5 verify: Opportunity follows the workspace's fees; `scores` never changes."""
    with Session(db_engine) as session:
        workspace_id = workspace(session, **LAMP_FEES, duty_default_bps=0)
        product_id = scored_lamp(session)
        session.commit()
        before = xmins(session)
    assert len(before) == 3
    first = scores(api, workspace_id, product_id)["opportunity"]
    assert (first["value"], first["explanation"]["confidence"]) == (65.7, 0.9)  # duty 0 is set

    with Session(db_engine) as session:
        session.get_one(WorkspaceSettings, workspace_id).payment_fee_bps = 2000
        session.commit()
    second = scores(api, workspace_id, product_id)["opportunity"]
    assert (
        second["explanation"]["components"][1]["raw"] == 0.3565
    )  # (2999 − 1150 − 630 − 150) / 2999
    assert second["value"] == 56.2  # (0.4 × 68.6 + 0.3 × 59.42 + 0.2 × 26.7) / 0.9

    with Session(db_engine) as session:
        assert xmins(session) == before  # no row rewritten, none added: Opportunity is not stored
        kinds = session.scalars(text("SELECT DISTINCT kind FROM scores")).all()
        assert sorted(kinds) == ["lifecycle", "saturation", "trend"]


@pytest.mark.db
@pytest.mark.parametrize("costs", [(2000, 500), (500, 2000)], ids=["dearer first", "cheaper first"])
def test_duty_not_set_costs_the_best_supplier_as_duty_0_does(
    api: TestClient, db_engine: Engine, costs: tuple[int, ...]
) -> None:
    """XR-66 (DEC-341): with duty unset, Opportunity costs the cheaper listing at duty 0 in either
    creation order, so it matches the duty-0 workspace but for confidence and the caution."""
    with Session(db_engine) as session:
        unset = workspace(session, **LAMP_FEES)
        zero = workspace(session, **LAMP_FEES, duty_default_bps=0)
        product_id = scored_lamp(session, costs)
        session.commit()

    found = {key: scores(api, key, product_id)["opportunity"] for key in (unset, zero)}
    for key, confidence, cautions in ((unset, 0.7, ["duty_not_set"]), (zero, 0.9, [])):
        explanation = found[key]["explanation"]
        assert found[key]["value"] == 69.8  # (0.4 × 68.6 + 0.3 × 100 + 0.2 × 26.7) / 0.9
        assert explanation["components"][1]["raw"] == 0.6075  # (2999 − 910 − 117 − 150) / 2999
        assert (explanation["confidence"], explanation["cautions"]) == (confidence, cautions)
        assert explanation["penalties"] == []  # never "margin below your floor" from the $20 one
    assert {**found[unset]["explanation"], "confidence": 0.9, "cautions": []} == found[zero][
        "explanation"
    ]


@pytest.mark.db
def test_each_workspace_reads_only_its_own_opportunity(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        a = workspace(session, **LAMP_FEES)
        b = workspace(session, **LAMP_FEES, duty_default_bps=4000)  # $2.96 duty
        unset = workspace(session)  # no settings row yet
        product_id = scored_lamp(session)
        session.commit()

    in_a = scores(api, a, product_id)["opportunity"]
    in_b = scores(api, b, product_id)["opportunity"]
    assert (in_a["value"], in_a["explanation"]["cautions"]) == (65.7, ["duty_not_set"])
    assert in_b["explanation"]["components"][1]["raw"] == 0.4288  # (1582 − 296) / 2999
    assert (in_b["explanation"]["cautions"], in_b["explanation"]["confidence"]) == ([], 0.9)
    assert in_b["value"] == 60.2
    none = scores(api, unset, product_id)["opportunity"]
    margin = none["explanation"]["components"][1]
    assert (margin["missing"], margin["source"]) == (True, None)  # no source yet
    assert none["explanation"]["missing"] == ["margin", "risk"]
    assert none["value"] == 54.6  # trend and room alone
    assert scores(api, a, product_id)["opportunity"] == in_a  # B's and C's reads changed nothing


@pytest.mark.db
def test_a_null_row_shows_its_reason_and_no_row_is_no_source_yet(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **LAMP_FEES)
        product_id = lamp(session)
        score(session, product_id, "trend", 70.0, day=YESTERDAY - timedelta(days=1))
        score(session, product_id, "trend", None, reason="no velocity growth")  # tonight: NULL
        score(session, product_id, "saturation", None, reason="no seller count")
        session.commit()

    body = scores(api, workspace_id, product_id)
    latest = body["latest"]
    assert latest["trend"]["value"] is None  # never the older 70.0 as if current
    assert latest["trend"]["explanation"]["reason"] == "no velocity growth"
    assert latest["saturation"]["explanation"]["reason"] == "no seller count"
    assert latest["lifecycle"] == {"value": None, "reason": NO_ROW}
    trend, margin, room, _ = body["opportunity"]["explanation"]["components"]
    assert (trend["missing"], trend["source"]) == (True, "trend")  # insufficient signal
    assert (room["missing"], room["source"]) == (True, "saturation")
    assert body["opportunity"]["value"] == 87.9  # margin alone: 100 × 0.5275 / 0.6
    assert body["opportunity"]["explanation"]["missing"] == ["trend", "saturation", "risk"]

    with Session(db_engine) as session:
        unscored = Product(name="Unscored")
        session.add(unscored)
        session.commit()
        unscored_id = unscored.id
    bare = scores(api, workspace_id, unscored_id)
    assert bare["opportunity"]["value"] is None
    assert bare["opportunity"]["explanation"]["reason"] == "no trend, margin or saturation yet"
    assert bare["history"] == []


@pytest.mark.db
def test_history_is_range_bounded_and_keyset_paginated(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **LAMP_FEES)
        product_id = lamp(session)
        for n in range(1, 41):
            score(session, product_id, "trend", 50.0 + n / 10, day=TODAY - timedelta(days=n))
        score(session, product_id, "trend", 61.0, model_version="001-fixture00000")  # a new version
        session.commit()

    month = scores(api, workspace_id, product_id, range="30d")
    days = [row["day"] for row in month["history"]]
    assert month["start"] == (TODAY - timedelta(days=29)).isoformat()
    assert len(days) == 30  # days 1–29 and yesterday's two versions
    assert days == sorted(days, reverse=True) and min(days) == month["start"]
    assert [r["model_version"] for r in month["history"][:2]] == [
        "001-fixture00000",
        "000-fixture00000",
    ]
    assert month["latest"]["trend"]["value"] == 61.0  # the newest computation of the latest day

    seen, cursor, pages = [], None, 0
    while True:
        page = scores(
            api,
            workspace_id,
            product_id,
            range="all",
            limit=15,
            **({"cursor": cursor} if cursor else {}),
        )
        seen += [(row["day"], row["model_version"]) for row in page["history"]]
        pages += 1
        if (cursor := page["next_cursor"]) is None:
            break
    assert (pages, len(seen), len(set(seen))) == (3, 41, 41)
    assert page["start"] is None
    bad = scores(api, workspace_id, product_id, 422, cursor=json.dumps(["x", 1]))
    assert bad["code"] == "invalid_cursor"


@pytest.mark.db
def test_unknown_is_404_and_merged_redirects(api: TestClient, db_engine: Engine) -> None:
    with Session(db_engine) as session:
        workspace_id = workspace(session, **LAMP_FEES)
        survivor = Product(name="Survivor")
        session.add(survivor)
        session.flush()
        merged = Product(name="Merged", merged_into_id=survivor.id)
        session.add(merged)
        session.commit()
        survivor_id, merged_id = survivor.id, merged.id
    scores(api, workspace_id, uuid4(), 404)
    assert isinstance(api.app, FastAPI)
    response = api.get(f"/v1/products/{merged_id}/scores?range=7d", follow_redirects=False)
    assert response.status_code == 308
    assert response.headers["location"] == f"../{survivor_id}/scores?range=7d"
