from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pulso_core.alerts import evaluate
from pulso_core.models import (
    Alert,
    AlertRule,
    CollectionGap,
    CollectorRun,
    Listing,
    ListingSnapshot,
    Product,
    ProductTest,
    RawPayload,
    ShippingOption,
    Supplier,
    Workspace,
)

# Alert rules engine (WF-4 part a, DEC-324): crossing, hysteresis, dedupe, gaps and no_source.

CJ = 2  # seeded source id
T0 = datetime(2026, 11, 2, 6, tzinfo=UTC)


def day(n: int) -> datetime:
    return T0 + timedelta(days=n)


def observe(session: Session, model: type[Any], at: datetime, **values: Any) -> None:
    run = CollectorRun(source_id=CJ, trigger="manual", status="success")
    session.add(run)
    session.flush()
    payload = RawPayload(
        source_id=CJ, run_id=run.id, captured_at=at, request={}, bytes=1, sha256=uuid4().hex * 2
    )
    session.add(payload)
    session.flush()
    session.add(model(captured_at=at, raw_payload_id=payload.id, observed_for=at.date(), **values))
    session.flush()


def snap(session: Session, listing_id: int, at: datetime, **values: Any) -> None:
    observe(
        session, ListingSnapshot, at, listing_id=listing_id, values_hash="h", currency="USD",
        **values,
    )  # fmt: skip


def quote(session: Session, listing_id: int, at: datetime, cost: int) -> None:
    observe(
        session, ShippingOption, at, listing_id=listing_id, destination_country="US",
        method="CJPacket", cost_minor=cost, currency="USD",
    )  # fmt: skip


def offer(session: Session) -> tuple[UUID, int]:
    """A product with one live CJ supplier listing."""
    product = Product(name="Sunset lamp")
    supplier = Supplier(platform="cj", external_id=uuid4().hex, name="CJ Dropshipping")
    session.add_all([product, supplier])
    session.flush()
    listing = Listing(
        source_id=CJ,
        external_id=uuid4().hex,
        url="https://cjdropshipping.example.test/p",
        title="Sunset lamp",
        product_id=product.id,
        supplier_id=supplier.id,
    )
    session.add(listing)
    session.flush()
    return product.id, listing.id


def workspace(session: Session) -> UUID:
    row = Workspace(name="Workspace")
    session.add(row)
    session.flush()
    return row.id


def rule(session: Session, ws: UUID, kind: str, target: tuple[str, object], **values: Any) -> UUID:
    row = AlertRule(
        workspace_id=ws, name=kind, type=kind, target_type=target[0], target_id=str(target[1]),
        **values,
    )  # fmt: skip
    session.add(row)
    session.flush()
    return row.id


def alerts(session: Session, ws: UUID, rule_id: UUID | None = None) -> list[Alert]:
    query = select(Alert).where(Alert.workspace_id == ws).order_by(Alert.id)
    if rule_id is not None:
        query = query.where(Alert.rule_id == rule_id)
    return list(session.scalars(query))


@pytest.mark.db
def test_a_cost_past_its_threshold_fires_once_and_again_only_after_crossing_back(
    db_engine: Engine,
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        product_id, listing = offer(session)
        cost = rule(session, ws, "supplier_price_change", ("supplier_offer", listing))
        muted = rule(session, ws, "supplier_price_change", ("supplier_offer", listing))
        session.get_one(AlertRule, muted).muted_until = day(99)
        off = rule(session, ws, "supplier_price_change", ("product", product_id), enabled=False)
        snap(session, listing, day(0), price_min_minor=1000)
        assert evaluate(session, ws, day(0)) == {cost: "ok"}  # first sight: the reference
        snap(session, listing, day(1), price_min_minor=1100)
        evaluate(session, ws, day(1))
        [first] = alerts(session, ws)
        assert (first.rule_id, first.type, first.entity_type) == (
            cost,
            "supplier_price_change",
            "supplier_offer",
        )
        assert first.entity_id == str(listing)
        assert first.dedupe_key == f"{cost}:supplier_offer:{listing}:2026-11-03"
        assert first.fired_at == day(1)
        assert first.payload["old"] == {
            "value": 1000,
            "currency": "USD",
            "as_of": day(0).isoformat(),
        }
        assert first.payload["new"]["value"] == 1100
        assert first.payload["new"]["source"] == "cj"
        assert first.payload["threshold"] == {"pct": 5}
        assert first.payload["as_of"] == {"cj": day(1).isoformat()}
        assert first.payload["link"] == f"/products/{product_id}/suppliers"
        assert session.get_one(AlertRule, cost).armed is False
        for n in range(2, 12):  # ten more evaluations past the threshold
            snap(session, listing, day(n), price_min_minor=1100 + n)
            evaluate(session, ws, day(n))
        snap(session, listing, day(12), price_min_minor=1048)  # 4.8%: inside the 4.75-5% band
        evaluate(session, ws, day(12))
        snap(session, listing, day(13), price_min_minor=1100)
        evaluate(session, ws, day(13))
        assert len(alerts(session, ws)) == 1
        snap(session, listing, day(14), price_min_minor=1040)  # 4%: back past the band, re-arms
        evaluate(session, ws, day(14))
        assert session.get_one(AlertRule, cost).armed is True
        snap(session, listing, day(15), price_min_minor=940)  # -6% crosses too
        evaluate(session, ws, day(15))
        second = alerts(session, ws)[1:]
        assert [a.payload["new"]["value"] for a in second] == [940]
        assert second[0].payload["old"]["value"] == 1000
        assert alerts(session, ws, muted) == alerts(session, ws, off) == []
        assert session.get_one(AlertRule, off).last_evaluated_at is None
        assert session.get_one(AlertRule, cost).last_evaluated_at == day(15)


@pytest.mark.db
def test_rerunning_an_evaluation_inserts_no_duplicate(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        _, listing = offer(session)
        cost = rule(session, ws, "supplier_price_change", ("supplier_offer", listing))
        snap(session, listing, day(0), price_min_minor=1000)
        evaluate(session, ws, day(0))
        before = dict(session.get_one(AlertRule, cost).last_value or {})
        snap(session, listing, day(1), price_min_minor=1200)
        evaluate(session, ws, day(1))
        evaluate(session, ws, day(1))
        assert len(alerts(session, ws)) == 1
        # Even with the rule's state lost, the dedupe key keeps the crossing to one row.
        session.get_one(AlertRule, cost).last_value = before
        session.get_one(AlertRule, cost).armed = True
        session.flush()
        evaluate(session, ws, day(1))
        assert len(alerts(session, ws)) == 1


@pytest.mark.db
def test_a_testing_product_gets_default_cost_freight_and_stock_alerts(
    db_engine: Engine,
) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        product_id, listing = offer(session)
        session.add(ProductTest(workspace_id=ws, product_id=product_id, stage="testing"))
        snap(session, listing, day(0), price_min_minor=1000, available=True, stock=40)
        quote(session, listing, day(0), 500)
        statuses = evaluate(session, ws, day(0))
        defaults = {
            r.type: r.id
            for r in session.scalars(select(AlertRule).where(AlertRule.workspace_id == ws))
        }
        assert set(defaults) == {"supplier_price_change", "freight_change", "supplier_stock_out"}
        assert statuses == dict.fromkeys(defaults.values(), "ok")
        evaluate(session, ws, day(0))
        assert session.scalar(select(func.count()).select_from(AlertRule)) == 3  # seeded once
        snap(session, listing, day(1), price_min_minor=1100, available=False, stock=0)
        quote(session, listing, day(1), 600)
        evaluate(session, ws, day(1))
        evaluate(session, ws, day(2))
        fired = {a.type: a for a in alerts(session, ws)}
        assert set(fired) == set(defaults)
        cost = fired["supplier_price_change"]
        assert cost.rule_id == defaults["supplier_price_change"]
        assert (cost.payload["old"]["value"], cost.payload["new"]["value"]) == (1000, 1100)
        assert (
            fired["freight_change"].payload["old"]["value"],
            fired["freight_change"].payload["new"]["value"],
        ) == (500, 600)
        stock = fired["supplier_stock_out"].payload
        assert (stock["old"]["value"], stock["new"]["value"], stock["threshold"]) == (
            True,
            False,
            {},
        )


@pytest.mark.db
def test_a_testing_change_across_a_collection_gap_is_skipped(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        product_id, listing = offer(session)
        session.add(ProductTest(workspace_id=ws, product_id=product_id, stage="testing"))
        own = rule(session, ws, "supplier_price_change", ("supplier_offer", listing))
        snap(session, listing, day(0), price_min_minor=1000)
        evaluate(session, ws, day(0))
        [default] = session.scalars(
            select(AlertRule.id).where(
                AlertRule.target_type == "test", AlertRule.type == "supplier_price_change"
            )
        )
        gap = CollectionGap(
            source_id=CJ, slot_key="2026-11-02T12", slot_start=day(0) + timedelta(hours=6),
            slot_end=day(0) + timedelta(hours=12), reason="missed", detected_at=day(1),
        )  # fmt: skip
        later = CollectionGap(
            source_id=CJ, slot_key="2026-11-02T18", slot_start=day(0) + timedelta(hours=12),
            slot_end=day(0) + timedelta(hours=18), reason="missed", detected_at=day(5),
        )  # fmt: skip
        session.add_all([gap, later])
        snap(session, listing, day(1), price_min_minor=1100)
        assert evaluate(session, ws, day(1))[default] == "skipped"
        assert alerts(session, ws, default) == []
        assert session.get_one(AlertRule, default).last_value["skipped"] == {  # type: ignore[index]
            "reason": "gap",
            "from": gap.slot_start.isoformat(),
            "to": gap.slot_end.isoformat(),  # the gap known by as_of, not the one found later
        }
        assert len(alerts(session, ws, own)) == 1  # only Testing rules are gap-aware (R-23)
        evaluate(session, ws, day(1) + timedelta(hours=1))  # no new observation: still held
        assert alerts(session, ws, default) == []
        snap(session, listing, day(2), price_min_minor=1100)  # a gap-free window confirms it
        assert evaluate(session, ws, day(2))[default] == "ok"
        assert [a.payload["new"]["as_of"] for a in alerts(session, ws, default)] == [
            day(2).isoformat()
        ]


@pytest.mark.db
def test_a_rule_without_a_source_never_fires_and_reports_no_source(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws = workspace(session)
        lonely = Product(name="No supplier")
        session.add(lonely)
        session.flush()
        _, listing = offer(session)
        none = rule(session, ws, "supplier_price_change", ("product", lonely.id))
        stock = rule(session, ws, "supplier_stock_out", ("supplier_offer", listing))
        back = rule(session, ws, "back_in_stock", ("supplier_offer", listing))
        snap(session, listing, day(0), price_min_minor=1000)  # CJ's catalog: no stock fields
        snap(session, listing, day(1), price_min_minor=900)
        assert evaluate(session, ws, day(1)) == {
            none: "no_source",
            stock: "no_source",
            back: "no_source",
        }
        snap(session, listing, day(2), available=False)
        snap(session, listing, day(3), stock=7)
        assert evaluate(session, ws, day(2))[back] == "ok"  # first sight: out of stock
        evaluate(session, ws, day(3))
        assert [a.rule_id for a in alerts(session, ws)] == [back]
        assert alerts(session, ws)[0].payload["new"]["value"] is True
        snap(session, listing, day(4), stock=0)  # out again: old is the last state, not the first
        evaluate(session, ws, day(4))
        out = alerts(session, ws, stock)[0].payload
        assert (out["old"], out["new"]["value"]) == (
            {"value": True, "as_of": day(3).isoformat()},
            False,
        )


@pytest.mark.db
def test_rules_and_alerts_stay_in_their_workspace(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        a, b = workspace(session), workspace(session)
        _, listing = offer(session)
        rule_a = rule(session, a, "supplier_price_change", ("supplier_offer", listing))
        rule_b = rule(session, b, "supplier_price_change", ("supplier_offer", listing))
        snap(session, listing, day(0), price_min_minor=1000)
        snap(session, listing, day(1), price_min_minor=2000)
        assert evaluate(session, a, day(0)) == {rule_a: "ok"}
        evaluate(session, a, day(1))
        assert [x.rule_id for x in alerts(session, a)] == [rule_a]
        assert alerts(session, b) == []
        assert session.get_one(AlertRule, rule_b).last_evaluated_at is None
        session.commit()
        session.add(
            Alert(
                workspace_id=a,
                rule_id=rule_b,
                type="supplier_price_change",
                entity_type="supplier_offer",
                entity_id="1",
                dedupe_key="x",
                payload={},
            )  # fmt: skip
        )
        with pytest.raises(IntegrityError):  # an alert can't name another workspace's rule
            session.flush()
        session.rollback()
        session.delete(session.get_one(AlertRule, rule_a))
        session.flush()
        [kept] = alerts(session, a)  # deleting a rule keeps its alerts
        assert kept.rule_id is None
