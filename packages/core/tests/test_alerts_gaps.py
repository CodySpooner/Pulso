from datetime import UTC, datetime, time, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.alerts import evaluate
from pulso_core.models import (
    Alert,
    AlertRule,
    CollectionGap,
    CollectorRun,
    Listing,
    Product,
    ProductTest,
    RawPayload,
    ShippingOption,
    Workspace,
)
from pulso_sources.cj import CJAdapter, Record, transport

# R-23 gap holds over CJ's change-only catalog snapshots (XR-63, XR-64, DEC-335). Prices go
# through the real CJAdapter.upsert, so a night with an unchanged price writes no snapshot row.

CJ = 2  # seeded source id
NIGHT = datetime(2026, 11, 2, 4, tzinfo=UTC)  # the cj.catalog slot


def at(n: int) -> datetime:
    return NIGHT + timedelta(days=n)


def midnight(n: int) -> datetime:
    return datetime.combine(at(n).date(), time(), UTC)


def cutoff(n: int) -> datetime:  # the nightly chain's as_of for night n: d+1 00:00Z
    return midnight(n + 1)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        transport, "HTTPSConnection", Mock(side_effect=AssertionError("No live HTTP"))
    )


def capture_in_run(session: Session, start: datetime, slot: str | None) -> RawPayload:
    """A complete, successful 5-minute CJ run from `start`, capturing a minute in."""
    run = CollectorRun(
        source_id=CJ, trigger="schedule" if slot else "manual", slot_key=slot, status="success",
        complete=True, started_at=start, finished_at=start + timedelta(minutes=5),
    )  # fmt: skip
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=CJ, run_id=run.id, captured_at=start + timedelta(minutes=1), request={},
        bytes=1, sha256=uuid4().hex * 2,
    )  # fmt: skip
    session.add(payload)
    session.flush()
    return payload


def capture(session: Session, n: int, price: int) -> int:
    """Night n's cj.catalog run sees the offer at `price`; returns the snapshot rows written."""
    payload = capture_in_run(session, at(n), f"catalog:{at(n).date()}")
    record = Record(
        external_id="lamp", title="Sunset lamp", price_min_minor=price, price_max_minor=price,
        listed_count=None,
    )  # fmt: skip
    adapter = CJAdapter()
    return adapter.upsert(
        session, [record], payload, parser_version=adapter.parser_version
    ).inserted


def quote(session: Session, n: int, cost: int) -> None:
    """A tracked freight run quotes the offer on night n; quotes are written per capture."""
    payload = capture_in_run(session, at(n) + timedelta(hours=2), None)
    session.add(
        ShippingOption(
            listing_id=session.scalars(select(Listing.id)).one(),
            destination_country="US",
            method="CJPacket",
            cost_minor=cost,
            currency="USD",
            captured_at=payload.captured_at,
            raw_payload_id=payload.id,
            observed_for=payload.captured_at.date(),
        )
    )
    session.flush()


def offline(session: Session, n: int, detected: datetime | None = None) -> None:
    """The PC is off on night n: no run, and the audit writes a host_offline gap on its return."""
    session.add(
        CollectionGap(
            source_id=CJ,
            slot_key=f"catalog:{at(n).date()}",
            slot_start=midnight(n),
            slot_end=midnight(n + 1),
            reason="host_offline",
            detected_at=detected or at(n + 1) - timedelta(minutes=30),
        )
    )
    session.flush()


def offer_in_test(session: Session) -> tuple[UUID, UUID]:
    """A workspace testing a product whose one CJ offer is first seen at 1000 on night 0."""
    ws, product = Workspace(name="Workspace"), Product(name="Sunset lamp")
    session.add_all([ws, product])
    session.flush()
    session.add(ProductTest(workspace_id=ws.id, product_id=product.id, stage="testing"))
    assert capture(session, 0, 1000) == 1
    session.execute(update(Listing).values(product_id=product.id))
    evaluate(session, ws.id, cutoff(0))
    return ws.id, default(session, ws.id, "supplier_price_change")


def default(session: Session, ws: UUID, kind: str) -> UUID:
    return session.scalars(
        select(AlertRule.id).where(
            AlertRule.workspace_id == ws, AlertRule.target_type == "test", AlertRule.type == kind
        )
    ).one()


def alerts(session: Session, rule_id: UUID) -> list[Alert]:
    return list(session.scalars(select(Alert).where(Alert.rule_id == rule_id).order_by(Alert.id)))


def span(n: int) -> dict[str, str]:
    return {"reason": "gap", "from": midnight(n).isoformat(), "to": midnight(n + 1).isoformat()}


@pytest.mark.db
def test_a_gap_a_week_before_a_price_change_does_not_hold_it(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, cost = offer_in_test(session)
        offline(session, 3)
        for n in (1, 2, *range(4, 11)):
            assert capture(session, n, 1100 if n == 10 else 1000) == (n == 10)
            assert evaluate(session, ws, cutoff(n))[cost] == "ok"
        [alert] = alerts(session, cost)
        assert alert.dedupe_key == f"{cost}:supplier_offer:{alert.entity_id}:2026-11-12"
        assert (alert.payload["old"]["value"], alert.payload["new"]["value"]) == (1000, 1100)
        assert alert.fired_at == cutoff(10)


@pytest.mark.db
def test_a_gap_the_night_before_a_change_holds_it_until_a_gap_free_run_sees_it_again(
    db_engine: Engine,
) -> None:
    with Session(db_engine) as session:
        ws, cost = offer_in_test(session)
        for n in range(1, 9):
            capture(session, n, 1000)
            evaluate(session, ws, cutoff(n))
        offline(session, 9)
        assert capture(session, 10, 1100) == 1
        rule = session.get_one(AlertRule, cost)
        for _ in range(2):  # a re-run with no new data keeps the hold and its span (XR-64)
            assert evaluate(session, ws, cutoff(10))[cost] == "skipped"
            assert rule.last_value["skipped"] == span(9)  # type: ignore[index]
        assert alerts(session, cost) == []
        assert capture(session, 11, 1100) == 0  # unchanged: CJ writes no snapshot row
        finished = at(11) + timedelta(minutes=5)
        assert evaluate(session, ws, finished)[cost] == "skipped"  # a run ending at as_of: unread
        assert evaluate(session, ws, cutoff(11))[cost] == "ok"
        [alert] = alerts(session, cost)
        assert alert.dedupe_key.endswith(":2026-11-12")  # the crossing's date, not the run's
        assert (alert.payload["old"]["value"], alert.payload["new"]["value"]) == (1000, 1100)
        assert alert.payload["new"]["as_of"] == (at(10) + timedelta(minutes=1)).isoformat()
        assert "skipped" not in rule.last_value  # type: ignore[operator]
        assert rule.armed is False


@pytest.mark.db
def test_a_gap_after_a_held_crossing_waits_for_the_next_gap_free_run(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, cost = offer_in_test(session)
        offline(session, 1)
        capture(session, 2, 1100)
        assert evaluate(session, ws, cutoff(2))[cost] == "skipped"
        offline(session, 3)
        capture(session, 4, 1100)  # back after another gap: not yet a gap-free re-observation
        assert evaluate(session, ws, cutoff(4))[cost] == "skipped"
        assert session.get_one(AlertRule, cost).last_value["skipped"] == span(1)  # type: ignore[index]
        capture(session, 5, 1100)
        assert evaluate(session, ws, cutoff(5))[cost] == "ok"
        assert [a.dedupe_key[-10:] for a in alerts(session, cost)] == ["2026-11-04"]


@pytest.mark.db
def test_nothing_captured_or_detected_at_as_of_is_read(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, cost = offer_in_test(session)
        offline(session, 1, detected=cutoff(2))  # found only at the cutoff
        capture(session, 2, 1100)
        seen = at(2) + timedelta(minutes=1)
        assert evaluate(session, ws, seen)[cost] == "ok"  # captured at as_of: not read yet
        assert alerts(session, cost) == []
        assert evaluate(session, ws, cutoff(2))[cost] == "ok"  # the gap isn't known before it
        [alert] = alerts(session, cost)
        assert alert.fired_at == cutoff(2)


@pytest.mark.db
def test_freight_holds_from_the_last_quote_and_only_a_new_quote_confirms_it(
    db_engine: Engine,
) -> None:
    with Session(db_engine) as session:
        ws, _ = offer_in_test(session)
        quote(session, 0, 500)
        evaluate(session, ws, cutoff(0))
        freight = default(session, ws, "freight_change")
        offline(session, 1)
        capture(session, 2, 1000)  # a complete catalog run quotes no freight
        quote(session, 3, 600)
        assert evaluate(session, ws, cutoff(3))[freight] == "skipped"  # from the last quote
        capture(session, 4, 1000)
        assert evaluate(session, ws, cutoff(4))[freight] == "skipped"
        quote(session, 5, 600)
        assert evaluate(session, ws, cutoff(5))[freight] == "ok"
        assert [a.dedupe_key[-10:] for a in alerts(session, freight)] == ["2026-11-07"]
