from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import AlertRule, Listing, Product, Supplier, User, Workspace

# Alert rules (WF-4 part a, DEC-324): the rules endpoints; the inbox is WF-4a2.

As = Callable[[str], TestClient]
T0 = datetime(2026, 11, 2, 6, tzinfo=UTC)


@pytest.fixture
def setup(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, object]]:
    """`as_("a")` makes the next requests workspace A's. ids: product, offer (a supplier
    listing), shop (a store listing) and the workspaces."""
    with Session(db_engine) as session:
        users = {key: User(clerk_user_id=f"user_{key}") for key in "ab"}
        workspaces = {key: Workspace(name=f"Workspace {key}") for key in "ab"}
        product = Product(name="Sunset lamp")
        supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ")
        session.add_all([*users.values(), *workspaces.values(), product, supplier])
        session.flush()
        offer = Listing(
            source_id=2, external_id="o", url="https://s.example.test/o", title="x",
            product_id=product.id, supplier_id=supplier.id,
        )  # fmt: skip
        shop = Listing(source_id=1, external_id="s", url="https://s.example.test/s", title="x")
        session.add_all([offer, shop])
        session.flush()
        ids: dict[str, object] = {"product": product.id, "offer": offer.id, "shop": shop.id}
        session.commit()
        principals = {key: Principal(users[key].id, workspaces[key].id) for key in "ab"}
        ids |= {f"workspace_{key}": workspace.id for key, workspace in workspaces.items()}

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


@pytest.mark.db
def test_rules_crud_validation_and_isolation(
    setup: tuple[As, dict[str, object]], db_engine: Engine
) -> None:
    as_, ids = setup
    client = as_("a")
    body = {"name": "Lamp cost", "type": "supplier_price_change", "target_type": "product"}
    made = client.post("/v1/alert-rules", json=body | {"target_id": str(ids["product"]).upper()})
    assert made.status_code == 201, made.text
    rule = made.json()
    assert rule["target_id"] == str(ids["product"])  # normalized
    assert rule["params"] == {"pct": 5}
    assert (rule["enabled"], rule["armed"], rule["status"]) == (True, True, None)
    offer = {"target_type": "supplier_offer", "target_id": str(ids["offer"])}
    stock = client.post(
        "/v1/alert-rules", json=body | offer | {"type": "supplier_stock_out"}
    ).json()
    wrongs: list[tuple[dict[str, Any], int]] = [
        ({"target_id": str(uuid4())}, 404),  # no such product
        ({"target_type": "supplier_offer", "target_id": str(ids["shop"])}, 404),  # not a supplier
        ({"target_type": "supplier_offer", "target_id": str(2**63)}, 404),
        ({"target_id": "lamp"}, 422),
        ({"target_type": "test", "target_id": "1"}, 422),  # Testing rules are the defaults
        ({"type": "velocity_spike", "target_id": str(ids["product"])}, 422),
        ({"target_id": str(ids["product"]), "params": {"pct": 0}}, 422),
    ]
    for wrong, status in wrongs:
        assert client.post("/v1/alert-rules", json=body | wrong).status_code == status, wrong
    page = client.get("/v1/alert-rules?limit=1").json()
    assert [r["id"] for r in page["items"]] == [stock["id"]]  # newest first
    rest = client.get(f"/v1/alert-rules?limit=1&cursor={page['next_cursor']}").json()
    assert ([r["id"] for r in rest["items"]], rest["next_cursor"]) == ([rule["id"]], None)
    until = (T0 + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    patched = client.patch(
        f"/v1/alert-rules/{rule['id']}",
        json={"name": "Cost ±8%", "params": {"pct": 8}, "enabled": False, "muted_until": until},
    ).json()
    assert (patched["name"], patched["params"]) == ("Cost ±8%", {"pct": 8})
    assert (patched["enabled"], patched["muted_until"]) == (False, until)
    unmuted = client.patch(f"/v1/alert-rules/{rule['id']}", json={"muted_until": None})
    assert unmuted.json()["muted_until"] is None
    nulls: list[dict[str, Any]] = [{"name": None}, {"type": "back_in_stock"}, {"enabled": None}]
    for null in nulls:
        assert client.patch(f"/v1/alert-rules/{rule['id']}", json=null).status_code == 422
    with Session(db_engine) as session:  # a Testing default, as evaluate() seeds it
        default = AlertRule(
            workspace_id=ids["workspace_a"], name="Testing: freight change", type="freight_change",
            target_type="test", params={"pct": 5},
            last_value={"status": "skipped", "skipped": {"reason": "gap"}},
        )  # fmt: skip
        session.add(default)
        session.commit()
        default_id = default.id
    shown = client.get("/v1/alert-rules").json()["items"][0]
    assert (shown["id"], shown["status"]) == (str(default_id), "skipped")
    assert shown["skipped"] == {"reason": "gap"}
    assert client.delete(f"/v1/alert-rules/{default_id}").json()["code"] == "default_rule"
    client = as_("b")
    assert client.get("/v1/alert-rules").json() == {"items": [], "next_cursor": None}
    assert client.patch(f"/v1/alert-rules/{rule['id']}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/v1/alert-rules/{rule['id']}").status_code == 404
    client = as_("a")
    deleted = client.delete(f"/v1/alert-rules/{rule['id']}")
    assert (deleted.status_code, deleted.json()["id"]) == (200, rule["id"])
    assert client.patch(f"/v1/alert-rules/{rule['id']}", json={"name": "x"}).status_code == 404
    assert isinstance(UUID(stock["id"]), UUID)
