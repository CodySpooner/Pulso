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
from pulso_core.models import Alert, AlertRule, Listing, Product, Supplier, User, Workspace

# Alerts (WF-4 part a, DEC-324): the inbox and the rules endpoints.

As = Callable[[str], TestClient]
T0 = datetime(2026, 11, 2, 6, tzinfo=UTC)


@pytest.fixture
def setup(client: TestClient, db_engine: Engine) -> tuple[As, dict[str, object]]:
    """`as_("a")` makes the next requests workspace A's. ids: product, offer (a supplier
    listing), shop (a store listing), the workspaces, and alerts a1..a4 (A; a3 and a4 fire
    at the same time) and b1 (B)."""
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
        for key, (ws, kind, hours) in {
            "a1": ("a", "supplier_price_change", 0),
            "a2": ("a", "supplier_stock_out", 1),
            "a3": ("a", "supplier_price_change", 2),
            "a4": ("a", "freight_change", 2),
            "b1": ("b", "supplier_price_change", 3),
        }.items():
            row = Alert(
                workspace_id=workspaces[ws].id, type=kind, entity_type="supplier_offer",
                entity_id=str(offer.id), dedupe_key=key, fired_at=T0 + timedelta(hours=hours),
                payload={"old": {"value": 1000}, "new": {"value": 1100}},
            )  # fmt: skip
            session.add(row)
            session.flush()
            ids[key] = row.id
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


def inbox(client: TestClient, query: str = "") -> list[int]:
    response = client.get(f"/v1/alerts{query}")
    assert response.status_code == 200, response.text
    return [item["id"] for item in response.json()["items"]]


def unread(client: TestClient) -> int:
    count = client.get("/v1/alerts/unread-count").json()["count"]
    assert isinstance(count, int)
    return count


@pytest.mark.db
def test_inbox_pages_filters_reads_and_archives(setup: tuple[As, dict[str, object]]) -> None:
    as_, ids = setup
    a1, a2, a3, a4, b1 = (ids[key] for key in ("a1", "a2", "a3", "a4", "b1"))
    client = as_("a")
    assert inbox(client) == [a4, a3, a2, a1]  # newest first, then the higher id
    first = client.get("/v1/alerts?limit=2").json()
    assert [item["id"] for item in first["items"]] == [a4, a3]
    assert first["items"][0]["payload"]["new"] == {"value": 1100}
    assert inbox(client, f"?limit=2&cursor={first['next_cursor']}") == [a2, a1]
    walked: list[int] = []
    query = "?limit=1"
    while query:  # one a page: the cursor between a4 and a3 breaks the fired_at tie on id
        page = client.get(f"/v1/alerts{query}").json()
        walked += [item["id"] for item in page["items"]]
        query = page["next_cursor"] and f"?limit=1&cursor={page['next_cursor']}"
    assert walked == [a4, a3, a2, a1]
    assert client.get("/v1/alerts?cursor=nope").json()["code"] == "invalid_cursor"
    assert inbox(client, "?type=supplier_stock_out") == [a2]
    assert unread(client) == 4
    for path in ("read", "archive", "unarchive"):  # B's or an unknown id: 404, nothing changes
        for foreign in (b1, 2**62):
            response = client.post(f"/v1/alerts/{path}", json={"ids": [a1, foreign]})
            assert response.json()["code"] == "not_found", (path, foreign)
    assert (unread(client), inbox(client, "?archived=true")) == (4, [])
    assert client.post("/v1/alerts/read", json={"ids": [a1, a1]}).json() == {"count": 3}
    assert inbox(client, "?unread=true") == [a4, a3, a2]
    assert inbox(client, "?unread=false") == [a1]
    read_at = client.get("/v1/alerts?unread=false").json()["items"][0]["read_at"]
    assert client.post("/v1/alerts/archive", json={"ids": [a2, a3]}).json() == {"count": 1}
    assert inbox(client) == [a4, a1]
    assert inbox(client, "?archived=true") == [a3, a2]  # the same keyset, archived only
    assert inbox(client, "?archived=true&type=supplier_stock_out&unread=true") == [a2]
    archived = client.get("/v1/alerts?archived=true&limit=1").json()
    assert inbox(client, f"?archived=true&limit=1&cursor={archived['next_cursor']}") == [a2]
    assert client.post("/v1/alerts/unarchive", json={"ids": [a3, a1]}).json() == {"count": 2}
    assert inbox(client, "?archived=true") == [a2]
    assert inbox(client) == [a4, a3, a1]
    assert inbox(client, "?unread=true") == [a4, a3]
    assert client.post("/v1/alerts/read", json={"all": True}).json() == {"count": 0}
    page = client.get("/v1/alerts?unread=false").json()
    assert [item["id"] for item in page["items"]] == [a4, a3, a1]
    assert page["items"][-1]["read_at"] == read_at  # a1 keeps its first read time
    bad: list[dict[str, Any]] = [{}, {"ids": [a1], "all": True}, {"all": False}, {"ids": []}]
    for body in bad:
        assert client.post("/v1/alerts/read", json=body).status_code == 422
    assert client.post("/v1/alerts/archive", json={"ids": []}).status_code == 422
    assert client.post("/v1/alerts/unarchive", json={"ids": []}).status_code == 422
    client = as_("b")  # A's reads and archives never touched B's alert
    assert inbox(client) == [b1]
    assert unread(client) == 1
    assert client.post("/v1/alerts/unarchive", json={"ids": [a2]}).status_code == 404


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
