"""P2-35 end to end (DEC-278): the leakage fixture's observations, the feature job, then
Discover's momentum sort (vault Intelligence/Velocity & Acceleration)."""

import importlib.util
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.products import FAMILIES, NO_SIGNAL
from pulso_core.models import ProductDailyFeature
from pulso_ml.features.daily import cutoff, run


def leakage_fixture() -> ModuleType:
    """packages/ml's leakage fixture, loaded by path: test folders aren't packages here."""
    path = Path(__file__).parents[3] / "packages/ml/tests/test_leakage.py"
    spec = importlib.util.spec_from_file_location("leakage_fixture", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


leakage = leakage_fixture()
P: dict[str, UUID] = leakage.P


@pytest.fixture
def api(client: TestClient, db_engine: Engine) -> TestClient:
    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    client.app.dependency_overrides[get_db] = database
    client.app.dependency_overrides[current_principal] = lambda: Principal(uuid4(), uuid4())
    return client


@pytest.mark.db
def test_momentum_ranks_products_by_the_jobs_latest_growth(
    api: TestClient, db_engine: Engine
) -> None:
    pdf = ProductDailyFeature
    with Session(db_engine) as session:
        leakage.build(session)
        for i in range(8, 46):  # as ml.features backfills: day 8 has the first baseline (day 1)
            run(session, leakage.START + timedelta(days=i))
            session.commit()
        rows = session.scalars(
            select(pdf).where(pdf.velocity_7d.is_not(None), pdf.growth_7d.is_not(None))
        ).all()
        p2_newest = session.scalars(
            select(pdf).where(pdf.product_id == P["p2"]).order_by(pdf.feature_date.desc())
        ).first()
        p7_newest = session.scalars(
            select(pdf).where(pdf.product_id == P["p7"]).order_by(pdf.feature_date.desc())
        ).first()
    rank = list(FAMILIES)
    best = {}  # each product's latest day with a growth, then the best grade on it (DEC-239 c)
    for feature in sorted(rows, key=lambda r: (r.feature_date, -rank.index(r.family))):
        best[feature.product_id] = feature
    live = set(P.values()) - {P["p6"]}  # P6 merged into P5 on day 40
    expected = sorted(live & best.keys(), key=lambda p: (best[p].growth_7d, p), reverse=True)
    expected += sorted(live - best.keys(), reverse=True)  # insufficient signal sinks

    response = api.get("/v1/products", params={"sort": "momentum", "limit": 100})
    assert response.status_code == 200, response.json()
    items = response.json()["items"]
    assert [UUID(item["id"]) for item in items] == expected
    # P5 speeds up (C3 sells 8 a day from day 36, merged in on day 40); P2..P4 hold steady
    # (G7 0 on day 29, ids break the tie); P1's CJ dips on day 45, which outranks its Shopify
    # day 29 (the latest day first); P7 has a V7 since the split but no growth yet.
    assert expected == [P[name] for name in ["p5", "p4", "p3", "p2", "p1", "p7"]]
    for item in items:
        velocity, row = item["velocity"], best.get(UUID(item["id"]))
        if row is None:
            assert velocity == {"value": None, "reason": NO_SIGNAL}
            continue
        assert row.velocity_7d is not None
        assert (
            velocity["value"],
            velocity["growth"],
            velocity["family"],
            velocity["grade"],
            velocity["gap"],
            datetime.fromisoformat(velocity["as_of"]),
        ) == (
            round(row.velocity_7d),
            row.growth_7d,
            row.family,
            FAMILIES[row.family][0],
            row.has_gap,
            cutoff(row.feature_date),  # computed long after the day ended
        )
    # Unknown never reads 0: P2's listing oversells from day 36, so Discover keeps day 29's V7
    # with that day's as_of; P7's known V7 without a growth is still "insufficient signal".
    assert p2_newest is not None and p2_newest.velocity_7d is None
    assert p7_newest is not None and p7_newest.velocity_7d == 3 and p7_newest.growth_7d is None
