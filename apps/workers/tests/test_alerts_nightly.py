import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.logging import JsonFormatter
from pulso_core.models import (
    Alert,
    AlertRule,
    CollectionGap,
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    ProductTest,
    RawPayload,
    Score,
    Supplier,
    Workspace,
)
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_workers import ml
from pulso_workers.celery_app import app

# SC-6 evaluates alerts after each day's scores (DEC-334), on fixture rows only.

CJ = 2  # seeded source id
D = date(2026, 9, 10)


def at(day: date, hour: int) -> datetime:
    return datetime.combine(day, time(hour), UTC)


def snap(session: Session, listing_id: int, captured: datetime, price: int) -> None:
    run = CollectorRun(source_id=CJ, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=CJ, run_id=run.id, captured_at=captured, request={}, bytes=1,
        sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    session.add(
        ListingSnapshot(
            listing_id=listing_id,
            captured_at=captured,
            raw_payload_id=payload.id,
            observed_for=captured.date(),
            values_hash="h",
            currency="USD",
            price_min_minor=price,
        )  # fmt: skip
    )
    session.flush()


def offer(session: Session) -> tuple[UUID, int]:
    """A product with one live CJ supplier listing."""
    product = Product(name="Sunset lamp")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ Dropshipping")
    session.add_all([product, supplier])
    session.flush()
    listing = Listing(
        source_id=CJ, external_id=uuid4().hex, url="https://cjdropshipping.example.test/p",
        title="Sunset lamp", product_id=product.id, supplier_id=supplier.id,
    )  # fmt: skip
    session.add(listing)
    session.flush()
    return product.id, listing.id


def workspace(session: Session, id: UUID | None = None) -> UUID:
    row = Workspace(id=id or uuid4(), name="Workspace")
    session.add(row)
    session.flush()
    return row.id


def rule(session: Session, ws: UUID, target_id: object) -> UUID:
    row = AlertRule(
        workspace_id=ws, name="cost", type="supplier_price_change", target_type="supplier_offer",
        target_id=str(target_id),
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row.id


def alerts(session: Session, ws: UUID) -> list[tuple[UUID | None, datetime, str]]:
    query = select(Alert.rule_id, Alert.fired_at, Alert.dedupe_key).where(Alert.workspace_id == ws)
    return [tuple(row) for row in session.execute(query.order_by(Alert.id))]


def run(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    caplog: pytest.LogCaptureFixture,
    task: str,
    **kwargs: str,
) -> list[dict[str, Any]]:
    """Runs an ml task against the test database; returns its pulso.ml lines as JSON."""
    caplog.clear()
    caplog.set_level("INFO", logger="pulso.ml")
    caplog.handler.setFormatter(JsonFormatter())  # formatted at emit, while job_id is set
    monkeypatch.setattr(ml, "get_session", lambda: Session(engine))
    app.tasks[task].apply(kwargs=kwargs, task_id=f"job-{task}", throw=True)
    return [json.loads(line) for line in caplog.text.splitlines()]


def done(lines: list[dict[str, Any]]) -> list[str]:
    return [line["message"] for line in lines if line["message"].startswith("alerts_done")]


@pytest.fixture
def chain(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("FEATURES_ENABLED", "on")
    return monkeypatch


@pytest.mark.db
def test_the_chain_fires_one_alert_per_workspace_and_a_rerun_fires_nothing(
    db_engine: Engine, caplog: pytest.LogCaptureFixture, chain: pytest.MonkeyPatch
) -> None:
    with Session(db_engine) as session:
        product_id, listing = offer(session)
        a, b = workspace(session), workspace(session)
        mine = {ws: rule(session, ws, listing) for ws in (a, b)}
        session.add(ProductTest(workspace_id=b, product_id=product_id, stage="testing"))
        snap(session, listing, at(D - timedelta(days=1), 12), 1000)
        snap(session, listing, at(D, 12), 1100)
        session.add(  # B's Testing default holds the crossing over this gap (R-23)
            CollectionGap(
                source_id=CJ,
                slot_key="2026-09-10T06",
                slot_start=at(D, 6),
                slot_end=at(D, 8),
                reason="missed",
                detected_at=at(D, 9),
            )  # fmt: skip
        )
        session.commit()
    before = str(D - timedelta(days=1))
    assert done(run(chain, db_engine, caplog, "ml.features", start=before, end=before)) == [
        f"alerts_done day={before} workspaces=2 fired=0 skipped=0 failed=0"  # the reference
    ]
    assert done(run(chain, db_engine, caplog, "ml.features", start=str(D), end=str(D))) == [
        f"alerts_done day={D} workspaces=2 fired=2 skipped=1 failed=0"
    ]
    with Session(db_engine) as session:
        fired = {ws: alerts(session, ws) for ws in (a, b)}
        assert fired == {
            ws: [(mine[ws], cutoff(D), f"{mine[ws]}:supplier_offer:{listing}:{D}")] for ws in (a, b)
        }
    assert done(run(chain, db_engine, caplog, "ml.features", start=str(D), end=str(D))) == [
        f"alerts_done day={D} workspaces=2 fired=0 skipped=0 failed=0"
    ]
    with Session(db_engine) as session:
        assert {ws: alerts(session, ws) for ws in (a, b)} == fired


@pytest.mark.db
def test_a_backfill_evaluates_each_day_at_its_own_cutoff(
    db_engine: Engine, caplog: pytest.LogCaptureFixture, chain: pytest.MonkeyPatch
) -> None:
    first, middle = D - timedelta(days=2), D - timedelta(days=1)
    with Session(db_engine) as session:
        ws = workspace(session)
        (_, early), (_, late) = offer(session), offer(session)
        on_middle, on_last = rule(session, ws, early), rule(session, ws, late)
        for listing in (early, late):
            snap(session, listing, at(first, 12), 1000)
        snap(session, early, at(middle, 10), 1100)
        snap(session, late, cutoff(middle) + timedelta(hours=1), 1100)  # after middle's cutoff
        session.commit()
    lines = run(chain, db_engine, caplog, "ml.features", start=str(first), end=str(D))
    assert done(lines) == [
        f"alerts_done day={day} workspaces=1 fired={fired} skipped=0 failed=0"
        for day, fired in ((first, 0), (middle, 1), (D, 1))
    ]
    with Session(db_engine) as session:
        assert alerts(session, ws) == [
            (on_middle, cutoff(middle), f"{on_middle}:supplier_offer:{early}:{middle}"),
            (on_last, cutoff(D), f"{on_last}:supplier_offer:{late}:{D}"),
        ]
        assert session.get_one(AlertRule, on_last).last_evaluated_at == cutoff(D)


@pytest.mark.db
def test_a_failing_workspace_is_logged_and_neither_stops_the_others_nor_the_scores(
    db_engine: Engine, caplog: pytest.LogCaptureFixture, chain: pytest.MonkeyPatch
) -> None:
    with Session(db_engine) as session:
        product_id, listing = offer(session)
        # Ordered by id, so the failing workspace goes first.
        bad = workspace(session, UUID(int=1))
        good = workspace(session, UUID(int=2))
        rule(session, bad, listing)
        theirs = rule(session, good, listing)
        snap(session, listing, at(D - timedelta(days=1), 12), 1000)
        snap(session, listing, at(D, 12), 1100)
        session.execute(
            insert(ProductDailyFeature).values(
                product_id=product_id,
                feature_date=D,
                family="cj_stock",
                feature_version=FEATURE_VERSION,
                coverage=1,
                has_gap=False,
                gap_flags={"missed_runs": []},
            )
        )
        session.commit()
        rule(session, bad, "not-a-listing")  # created later, so evaluated after bad's good rule
        session.commit()
    run(chain, db_engine, caplog, "ml.scores", day=str(D - timedelta(days=1)))
    lines = run(chain, db_engine, caplog, "ml.scores", day=str(D))
    [failure] = [line for line in lines if line["level"] == "ERROR"]
    assert failure["message"] == f"alerts_failed day={D} workspace_id={bad}"
    assert failure["job_id"] == "job-ml.scores"
    assert "ValueError" in failure["exc_info"]
    assert done(lines) == [f"alerts_done day={D} workspaces=1 fired=1 skipped=0 failed=1"]
    with Session(db_engine) as session:
        assert alerts(session, bad) == []  # its good rule's alert went with the rollback
        assert [rule_id for rule_id, *_ in alerts(session, good)] == [theirs]
        assert session.scalar(select(func.count()).where(Score.date == D)) == 2  # trend, stage


@pytest.mark.db
@pytest.mark.parametrize("task", ["ml.features", "ml.scores"])
def test_with_features_off_nothing_is_evaluated(
    db_engine: Engine,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    task: str,
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        _, listing = offer(session)
        mine = rule(session, ws, listing)
        snap(session, listing, at(D, 12), 1000)
        session.commit()
    kwargs = {"start": str(D), "end": str(D)} if task == "ml.features" else {"day": str(D)}
    lines = run(monkeypatch, db_engine, caplog, task, **kwargs)
    assert done(lines) == []
    with Session(db_engine) as session:
        assert session.get_one(AlertRule, mine).last_evaluated_at is None
