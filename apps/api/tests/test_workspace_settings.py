from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
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
)

SHOPIFY, CJ = 1, 2  # seeded source ids
DAY = datetime(2026, 10, 23, 12, tzinfo=UTC)
BODY = {
    "payment_fee_bps": 290,
    "payment_fee_fixed_minor": 30,
    "shopify_fee_bps": 0,
    "default_cpa_minor": 1500,
    "target_margin_bps": 2000,
    "duty_default_bps": None,
    "returns_bps": 500,
    "customs_fee_minor": 0,
}
DEFAULTS = {
    **dict.fromkeys(BODY, 0),
    "duty_default_bps": None,
    "default_country": "US",
    "currency": "USD",
}


def as_principal(client: TestClient, workspace_id: UUID) -> TestClient:
    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), workspace_id)
    return client


def test_settings_require_a_session(client: TestClient) -> None:
    assert client.get("/v1/settings").status_code == 401
    assert client.patch("/v1/settings", json=BODY).status_code == 401


@pytest.mark.parametrize(
    "change",
    [
        *({key: -1} for key in BODY),
        *({key: 10001} for key in BODY if key.endswith("_bps") and key != "duty_default_bps"),
        {"duty_default_bps": 100_001},
        *({key: 2**63} for key in BODY if key.endswith("_minor")),
        {"payment_fee_bps": 2.5},
        {"payment_fee_bps": "290"},
        {"customs_fee_minor": True},
        {"target_margin_bps": None},
        {"default_country": "CA"},
        {"currency": "EUR"},
        {"default_country": None},
        {"workspace_id": str(uuid4())},
        {"ddp_default": True},
    ],
    ids=repr,
)
def test_patch_rejects_what_the_table_rejects(client: TestClient, change: dict[str, Any]) -> None:
    response = as_principal(client, uuid4()).patch("/v1/settings", json={**BODY, **change})
    assert response.status_code == 422
    problem = response.json()
    assert (problem["code"], problem["status"]) == ("validation_error", 422)
    assert problem["errors"]


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    return client


def workspace(session: Session, *, bare: bool = False) -> UUID:
    """A workspace with a default settings row, or with none when `bare`."""
    row = Workspace(name="Workspace")
    session.add(row)
    session.flush()
    if not bare:
        session.add(WorkspaceSettings(workspace_id=row.id))
    return row.id


@pytest.mark.db
def test_first_get_creates_the_row_with_the_table_defaults(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session, bare=True)
        session.commit()

    for _ in range(2):  # the second GET finds the row
        response = as_principal(api, ws).get("/v1/settings")
        assert response.status_code == 200, response.text
        assert response.json() == {**DEFAULTS, "workspace_id": str(ws)}
    with Session(db_engine) as session:
        assert session.scalar(select(func.count()).select_from(WorkspaceSettings)) == 1


@pytest.mark.db
def test_patch_round_trips_and_keeps_duty_not_set_apart_from_zero(
    api: TestClient, db_engine: Engine
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        session.commit()
    client = as_principal(api, ws)
    expected = {**BODY, "workspace_id": str(ws), "default_country": "US", "currency": "USD"}

    for duty in (0, None, 150_00, 100_000):  # 0 is set; null is not set; duty can pass 100%
        body = {**BODY, "duty_default_bps": duty}
        response = client.patch("/v1/settings", json=body)
        assert response.status_code == 200, response.text
        assert response.json() == {**expected, "duty_default_bps": duty}
        assert client.get("/v1/settings").json() == response.json()
        with Session(db_engine) as session:
            assert session.get_one(WorkspaceSettings, ws).duty_default_bps == duty

    # Leaving duty out keeps it; only an explicit null clears it.
    assert client.patch("/v1/settings", json={"returns_bps": 800}).json()["duty_default_bps"] == (
        100_000
    )
    # The locked market may be echoed back unchanged.
    locked = {"default_country": "US", "currency": "USD"}
    assert client.patch("/v1/settings", json=locked).status_code == 200


@pytest.mark.db
def test_workspace_a_put_never_changes_workspace_b(
    db_engine: Engine, api: TestClient, signed_token: Callable[[dict[str, Any]], str]
) -> None:
    a = {"Authorization": "Bearer " + signed_token({"sub": "user_a"})}
    b = {"Authorization": "Bearer " + signed_token({"sub": "user_b"})}
    a_id = api.get("/v1/me", headers=a).json()["workspace_id"]
    b_id = api.get("/v1/me", headers=b).json()["workspace_id"]
    assert a_id != b_id

    assert api.patch("/v1/settings", headers=a, json=BODY).status_code == 200
    assert api.get("/v1/settings", headers=b).json() == {**DEFAULTS, "workspace_id": b_id}
    # A forged workspace header is ignored: the principal's workspace is the only scope.
    forged = api.patch(
        "/v1/settings",
        headers={**b, "X-Workspace-ID": a_id},
        json={**BODY, "target_margin_bps": 4321},
    )
    assert forged.json()["workspace_id"] == b_id
    assert api.get("/v1/settings", headers=a).json()["target_margin_bps"] == 2000


def observe(session: Session, model: type[Any], source_id: int, **values: Any) -> Any:
    run = CollectorRun(source_id=source_id, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=source_id,
        run_id=run.id,
        captured_at=DAY,
        request={},
        bytes=1,
        sha256=uuid4().hex * 2,
    )
    session.add(payload)
    session.flush()
    row = model(captured_at=DAY, observed_for=DAY.date(), raw_payload_id=payload.id, **values)
    session.add(row)
    session.flush()
    return row


def lamp(session: Session) -> UUID:
    """A product at $29.99 in one store, with a $6.20 CJ listing and $4.85 US freight."""
    product = Product(name="Sunset lamp")
    store = Store(domain=f"{uuid4().hex}.example.test", platform="shopify")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ supplier")
    session.add_all([product, store, supplier])
    session.flush()
    for source_id, price, owner in ((SHOPIFY, 2999, {"store_id": store.id}), (CJ, 620, {})):
        listing = Listing(
            source_id=source_id,
            external_id=uuid4().hex,
            url="https://listing.example.test/p",
            title="Sunset lamp",
            product_id=product.id,
            supplier_id=supplier.id if source_id == CJ else None,
            **owner,
        )
        session.add(listing)
        session.flush()
        observe(
            session,
            ListingSnapshot,
            source_id,
            listing_id=listing.id,
            values_hash="h",
            currency="USD",
            price_min_minor=price,
        )
    observe(
        session,
        ShippingOption,
        CJ,
        listing_id=listing.id,
        destination_country="US",
        quantity=1,
        method="CJPacket",
        cost_minor=485,
        currency="USD",
    )
    return product.id


@pytest.mark.db
def test_a_fee_change_moves_the_next_profit_calc(api: TestClient, db_engine: Engine) -> None:
    """UX-10's verify, on POST /v1/profit/calc until Discover's best margin exists (UX-8 part c)."""
    with Session(db_engine) as session:
        ws = workspace(session)
        product_id = str(lamp(session))
        session.commit()
    client = as_principal(api, ws)

    def margin() -> Any:
        response = client.post("/v1/profit/calc", json={"product_id": product_id})
        assert response.status_code == 200, response.text
        return response.json()

    def save(**change: Any) -> None:
        assert client.patch("/v1/settings", json={**BODY, **change}).status_code == 200

    save(duty_default_bps=2000)
    before = margin()
    # 2999 − (620 + 485 + 124 duty) − (87 + 30 payment) − 150 returns
    assert (before["margin_minor"], before["payment_fee_minor"]) == (1503, 117)

    save(duty_default_bps=2000, payment_fee_bps=590)
    after = margin()
    assert (after["margin_minor"], after["payment_fee_minor"]) == (1413, 207)
    assert after["sources"]["payment_fee_bps"]["source"] == "settings"

    # Duty not set is not 0: the margin is withheld until it is set.
    save(duty_default_bps=None)
    assert (margin()["margin_minor"], margin()["missing"]) == (None, ["duty_not_set"])
    save(duty_default_bps=0)
    assert margin()["margin_minor"] == 1503 + 124
