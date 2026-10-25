"""imp-311 (DEC-287): a NUL character in free text answers a 422 problem, never a 500.

Postgres text can't hold NUL (XR-32). Body text and the shared `Brand` carry NoNulStr, so FastAPI
refuses them before any SQL. Query, path and cursor text that reaches a SQL parameter meets
the NUL DataError handler instead. Tabs and newlines pass both, as before."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import CollectorRun, Product, Source, User, Workspace

Case = tuple[str, str, dict[str, Any]]  # method, url, httpx keyword arguments


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> Iterator[tuple[TestClient, dict[str, Any]]]:
    with Session(db_engine) as session:
        user, workspace = User(clerk_user_id="user_a"), Workspace(name="A")
        product = Product(name="P")
        session.add_all([user, workspace, product])
        cj = session.scalars(select(Source).where(Source.key == "cj")).one()
        run = CollectorRun(source_id=cj.id, trigger="manual", status="success")
        session.add(run)
        session.commit()
        principal = Principal(user.id, workspace.id)
        ids = {"product": product.id, "run": run.id}

    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: principal
    yield client, ids


def send(client: TestClient, case: Case, ids: dict[str, Any]) -> Any:
    method, url, kwargs = case
    if kwargs.get("json", {}).get("product_id") == "{product}":
        kwargs = {"json": {**kwargs["json"], "product_id": str(ids["product"])}}
    return client.request(method, url.format(**ids), **kwargs)


def decision(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"json": {**action, "reason": reason}}


PAIR = {"action": "reject", "candidate_id": 1}
MERGE = {"action": "merge", "product_id": str(uuid4()), "into": str(uuid4())}
MOVE = {"action": "split", "listing_ids": [1]}
DECISIONS = "/v1/admin/matching/decisions"
BRANDS = "/v1/popular-products/brands"

# Typed with NoNulStr: the field, its NUL request, the same request with a tab or newline, and
# that request's status before and after imp-311.
TYPED: dict[str, tuple[tuple[str | int, ...], Case, Case, int]] = {
    "tag": (
        ("body", "tags", 1),
        ("PUT", "/v1/products/{product}/tags", {"json": {"tags": ["ok", "b\x00d"]}}),
        ("PUT", "/v1/products/{product}/tags", {"json": {"tags": ["ok", "b\td\ne"]}}),
        200,
    ),
    "note body": (
        ("body", "body"),
        ("POST", "/v1/products/{product}/notes", {"json": {"body": "a\x00b"}}),
        ("POST", "/v1/products/{product}/notes", {"json": {"body": "line\tone\nline two"}}),
        201,
    ),
    "pair reason": (
        ("body", "reject", "reason"),
        ("POST", DECISIONS, decision(PAIR, "a\x00b")),
        ("POST", DECISIONS, decision(PAIR, "a\tb\nc")),
        404,  # no such candidate: the reason passed validation
    ),
    "merge reason": (
        ("body", "merge", "reason"),
        ("POST", DECISIONS, decision(MERGE, "a\x00b")),
        ("POST", DECISIONS, decision(MERGE, "a\tb\nc")),
        404,
    ),
    "split reason": (
        ("body", "split", "reason"),
        ("POST", DECISIONS, decision(MOVE, "a\x00b")),
        ("POST", DECISIONS, decision(MOVE, "a\tb\nc")),
        409,  # no such listing
    ),
    "source reason": (
        ("body", "reason"),
        ("PATCH", "/v1/admin/sources/cj", {"json": {"enabled": False, "reason": "a\x00b"}}),
        ("PATCH", "/v1/admin/sources/cj", {"json": {"enabled": False, "reason": "a\tb\nc"}}),
        200,
    ),
    "brand rule": (
        ("body", "brand"),
        ("PUT", BRANDS, {"json": {"brand": "Ac\x00me", "action": "hide"}}),
        ("PUT", BRANDS, {"json": {"brand": "Ac\tme", "action": "hide"}}),
        200,
    ),
    "brand query": (
        ("query", "brand"),
        ("DELETE", BRANDS, {"params": {"brand": "Ac\x00me"}}),
        ("DELETE", BRANDS, {"params": {"brand": "Ac\tme"}}),
        200,
    ),
    "profit method": (
        ("body", "method"),
        ("POST", "/v1/profit/calc", {"json": {"product_id": "{product}", "method": "Sea\x00"}}),
        ("POST", "/v1/profit/calc", {"json": {"product_id": "{product}", "method": "Sea\tAir"}}),
        200,
    ),
    "search q": (
        ("query", "q"),
        ("GET", "/v1/search", {"params": {"q": "ab\x00cd"}}),
        ("GET", "/v1/search", {"params": {"q": "ab\tcd"}}),
        200,
    ),
}

# Not a model field: text that reaches a SQL parameter unchecked, so the handler answers.
HANDLED: dict[str, tuple[Case, Case, int]] = {
    "source key path": (
        ("PATCH", "/v1/admin/sources/c%00j", {"json": {"enabled": False}}),
        ("PATCH", "/v1/admin/sources/c%09j", {"json": {"enabled": False}}),
        404,
    ),
    "runs source": (
        ("GET", "/v1/admin/runs", {"params": {"source": "c\x00j"}}),
        ("GET", "/v1/admin/runs", {"params": {"source": "c\tj"}}),
        200,
    ),
    "run targets cursor": (
        ("GET", "/v1/admin/runs/{run}", {"params": {"cursor": '["a\\u0000", "b"]'}}),
        ("GET", "/v1/admin/runs/{run}", {"params": {"cursor": '["a\\t", "b\\n"]'}}),
        200,
    ),
    "candidates version": (
        ("GET", "/v1/admin/matching/candidates", {"params": {"version": "v\x001"}}),
        ("GET", "/v1/admin/matching/candidates", {"params": {"version": "v\t1"}}),
        200,
    ),
    "brand rules cursor": (
        ("GET", BRANDS, {"params": {"cursor": '"ac\\u0000me"'}}),
        ("GET", BRANDS, {"params": {"cursor": '"ac\\tme"'}}),
        200,
    ),
    "products source": (
        ("GET", "/v1/products", {"params": {"source": "c\x00j"}}),
        ("GET", "/v1/products", {"params": {"source": "c\tj"}}),
        200,
    ),
}


@pytest.mark.db
@pytest.mark.parametrize("name", TYPED)
def test_a_nul_in_a_typed_field_is_a_validation_422(
    api: tuple[TestClient, dict[str, Any]], name: str
) -> None:
    client, ids = api
    loc, nul, tab, status = TYPED[name]
    response = send(client, nul, ids)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["code"] == "validation_error"
    assert [(e["loc"], e["type"]) for e in problem["errors"]] == [
        (list(loc), "string_pattern_mismatch")
    ]
    assert send(client, tab, ids).status_code == status


@pytest.mark.db
@pytest.mark.parametrize("name", HANDLED)
def test_a_nul_reaching_sql_is_an_invalid_text_422(
    api: tuple[TestClient, dict[str, Any]], name: str
) -> None:
    client, ids = api
    nul, tab, status = HANDLED[name]
    response = send(client, nul, ids)
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert (response.json()["code"], response.json()["errors"]) == ("invalid_text", [])
    assert send(client, tab, ids).status_code == status


def test_other_data_errors_stay_500s(client: TestClient) -> None:
    def overflow() -> None:
        raise DataError("SELECT", None, psycopg.DataError("numeric field overflow"))

    assert isinstance(client.app, FastAPI)
    client.app.add_api_route("/overflow", overflow)
    response = client.get("/overflow")
    assert (response.status_code, response.json()["code"]) == (500, "internal_error")
