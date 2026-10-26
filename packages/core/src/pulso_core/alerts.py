"""Alert rules engine (WF-4 part a, DEC-324): `evaluate()` turns supplier observations into
alerts that fire once per threshold crossing.

A rule watches supplier offers (supplier listings): one offer, a product's live offers or, for
the R-23 defaults, the offers of every product with an open test. The first value a rule sees
for an offer is its reference. An armed offer fires when it moves past the threshold, and re-arms
once it is back past the hysteresis band. Testing rules hold back a crossing whose window holds a
collection gap known before `as_of` until a gap-free run sees the offer again (DEC-335). Every
read is strictly before `as_of`. The caller commits; the nightly chain (SC-6) calls this.

Score rules (DEC-353) watch a product, or a watchlist's products, through SC-6's stored rows,
never recomputing a score: `velocity_spike` the Lifecycle row's V7 against its prior 7 days,
suppressed while either window holds a gap, and `saturation_cross` the Saturation value.
"""

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Row, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.landed_cost_loader import STOCK_READ, in_stock
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
    Score,
    ShippingOption,
    Source,
    WatchlistItem,
)
from pulso_core.models.core import TEST_STAGES
from pulso_core.scores import latest as latest_scores

HYSTERESIS = Decimal("0.05")  # re-arm below threshold x (1 - 5%): the vault's guess
DEFAULT_PCT = 5
PCT = ("supplier_price_change", "freight_change")  # a % change from the reference
SCORED = {"velocity_spike": "lifecycle", "saturation_cross": "saturation"}  # the row each reads
SPIKE = {"pct": 50, "window_days": 7, "min_volume": 10}  # velocity_spike's defaults (DEC-353)
TYPES = (*PCT, "supplier_stock_out", "back_in_stock", *SCORED)  # in_stock() flips
OPEN = TEST_STAGES[:3]
TESTING: tuple[
    tuple[str, str, dict[str, int]], ...
] = (  # R-23: a workspace's default rules once it has an open test
    ("Testing: supplier cost change", "supplier_price_change", {"pct": DEFAULT_PCT}),
    ("Testing: freight change", "freight_change", {"pct": DEFAULT_PCT}),
    ("Testing: supplier stock-out", "supplier_stock_out", {}),
)
DONE = (CollectorRun.status == "success", CollectorRun.complete)


def offers(session: Session, rule: AlertRule) -> list[Row[Any]]:
    """The live supplier listings a rule watches, with their product."""
    query = select(Listing.id, Listing.product_id).where(
        Listing.supplier_id.is_not(None), Listing.delisted_at.is_(None)
    )
    if rule.target_type == "supplier_offer":
        query = query.where(Listing.id == int(str(rule.target_id)))
    elif rule.target_type == "product":
        query = query.where(Listing.product_id == UUID(str(rule.target_id)))
    else:  # test
        tests = select(ProductTest.product_id).where(
            ProductTest.workspace_id == rule.workspace_id, ProductTest.stage.in_(OPEN)
        )
        query = query.where(Listing.product_id.in_(tests))
    return list(session.execute(query.order_by(Listing.id)).all())


def latest(session: Session, rule_type: str, listing_id: int, as_of: datetime) -> Row[Any] | None:
    """The offer's newest observation the rule reads, captured before `as_of`."""
    snap: type[ListingSnapshot] | type[ShippingOption] = ListingSnapshot
    then: Any = ListingSnapshot.id.desc()
    reads: list[Any] = [ListingSnapshot.available, ListingSnapshot.stock]
    # A snapshot with no stock fields (CJ's catalog) says nothing about stock (DEC-348).
    where = [STOCK_READ]
    if rule_type == "supplier_price_change":
        reads = [ListingSnapshot.price_min_minor.label("minor")]
        where = [ListingSnapshot.price_min_minor.is_not(None)]
    elif rule_type == "freight_change":  # the newest capture's cheapest US quote for one unit
        snap, then = ShippingOption, ShippingOption.cost_minor
        reads = [ShippingOption.cost_minor.label("minor")]
        where = [ShippingOption.destination_country == "US", ShippingOption.quantity == 1]
    return session.execute(
        select(*reads, snap.currency, snap.captured_at, snap.raw_payload_id)
        .add_columns(RawPayload.source_id, Source.key.label("source"))
        .join(RawPayload, RawPayload.id == snap.raw_payload_id)
        .join(Source, Source.id == RawPayload.source_id)
        .where(snap.listing_id == listing_id, snap.captured_at < as_of, *where)
        .order_by(snap.captured_at.desc(), then)
        .limit(1)
    ).first()


def past(rule: AlertRule, ref: Any, value: Any) -> bool | None:
    """True past the threshold, False back past the re-arm band, None inside the band."""
    if rule.type == "velocity_spike":  # a rise of V7 over the prior 7 days, at the volume floor
        params = SPIKE | rule.params
        pct, rise = Decimal(str(params["pct"])), Decimal(str(value - ref)) * 100
        rise /= max(Decimal(str(ref)), Decimal(1))  # ponytail: a prior week of 0 reads as 1
        if rise >= pct and value >= params["min_volume"]:
            return True
        return False if rise < pct * (1 - HYSTERESIS) else None
    if rule.type == "saturation_cross":  # past the line in the rule's direction
        line = Decimal(str(rule.params["threshold"]))
        side = (Decimal(str(value)) - line) * (1 if rule.params["direction"] == "above" else -1)
        return True if side >= 0 else False if side < -line * HYSTERESIS else None
    if rule.type not in PCT:
        return bool(value) if rule.type == "back_in_stock" else not value
    pct = Decimal(str(rule.params.get("pct", DEFAULT_PCT)))
    change = Decimal(abs(value - ref) * 100) / max(ref, 1)  # ponytail: a 0 price reads as 1
    return True if change >= pct else False if change < pct * (1 - HYSTERESIS) else None


def gap(
    session: Session, source_id: int, start: datetime, end: datetime, as_of: datetime
) -> dict[str, str] | None:
    """The source's gaps detected before `as_of` that overlap (start, end], as one span."""
    first, last = session.execute(
        select(func.min(CollectionGap.slot_start), func.max(CollectionGap.slot_end)).where(
            CollectionGap.source_id == source_id,
            CollectionGap.detected_at < as_of,
            CollectionGap.slot_start < end,
            CollectionGap.slot_end > start,
        )
    ).one()
    return (
        None
        if first is None
        else {"reason": "gap", "from": first.isoformat(), "to": last.isoformat()}
    )


def since(session: Session, rule: AlertRule, row: Row[Any], state: dict[str, Any]) -> datetime:
    """Where a crossing's gap window starts: the source's newest complete run before the row, or
    the previous row if later. Snapshots are change-only, so that row is the last change; freight
    quotes are per capture, so for them it is the last capture."""
    start = datetime.fromisoformat(state["at"])
    if rule.type == "freight_change":
        return start
    run = session.scalar(
        select(func.max(CollectorRun.finished_at)).where(
            CollectorRun.source_id == row.source_id,
            *DONE,
            CollectorRun.finished_at < row.captured_at,
        )
    )
    return max(start, run) if run else start


def seen(session: Session, row: Row[Any], as_of: datetime) -> bool:
    """Whether a complete run of the row's source, started after it and finished before `as_of`,
    saw the offer again over a gap-free window (since the run before it). Change-only snapshots
    write no row for an unchanged value, so the run is the evidence."""
    # ponytail: a complete run of the source stands in for seeing this offer; per-offer evidence
    # needs a run -> listing capture record (a migration).
    start = row.captured_at
    for end in session.scalars(
        select(CollectorRun.finished_at)
        .where(CollectorRun.source_id == row.source_id, *DONE)
        .where(CollectorRun.started_at > start, CollectorRun.finished_at < as_of)
        .order_by(CollectorRun.finished_at)
    ):
        if not gap(session, row.source_id, start, cast(datetime, end), as_of):
            return True
        start = end
    return False


def fire(
    session: Session,
    rule: AlertRule,
    offer: Row[Any],
    state: dict[str, Any],
    row: Row[Any],
    value: Any,
    as_of: datetime,
) -> None:
    listing_id, product_id = offer
    money = {"currency": row.currency} if rule.type in PCT else {}
    at = row.captured_at.isoformat()
    payload = {
        "old": {"value": state["ref"], **money, "as_of": state["ref_at"]},
        "new": {
            "value": value,
            **money,
            "as_of": at,
            "source": row.source,
            "raw_payload_id": row.raw_payload_id,
        },
        "threshold": {"pct": rule.params.get("pct", DEFAULT_PCT)} if rule.type in PCT else {},
        "as_of": {row.source: at},
        "link": f"/products/{product_id}/suppliers" if product_id else None,
    }
    crossed = row.captured_at.astimezone(UTC).date()
    session.execute(
        insert(Alert)
        .values(
            workspace_id=rule.workspace_id,
            rule_id=rule.id,
            type=rule.type,
            entity_type="supplier_offer",
            entity_id=str(listing_id),
            dedupe_key=f"{rule.id}:supplier_offer:{listing_id}:{crossed}",
            fired_at=as_of,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def step(session: Session, rule: AlertRule, as_of: datetime) -> str:
    """Advance each watched offer's state, fire its armed crossings and record the status."""
    before = (rule.last_value or {}).get("entities", {})
    entities: dict[str, dict[str, Any]] = {}
    status, skipped = "no_source", None
    for offer in offers(session, rule):
        row = latest(session, rule.type, offer.id, as_of)
        if row is None:
            continue
        status = "ok" if status == "no_source" else status
        key, at = f"supplier_offer:{offer.id}", row.captured_at.isoformat()
        value = row.minor if rule.type in PCT else in_stock(row.available, row.stock)
        state = before.get(key)
        if state is None or state["currency"] != row.currency:  # first sight: the reference
            armed = past(rule, value, value) is not True
            entities[key] = {"ref": value, "ref_at": at, "value": value, "at": at,
                             "currency": row.currency, "armed": armed}  # fmt: skip
            continue
        entities[key] = state = dict(state)
        if row.captured_at > datetime.fromisoformat(state["at"]):  # a new observation
            state.pop("held", None)
            level = past(rule, state["ref"], value)
            if state["armed"] and level:
                held = rule.target_type == "test" and gap(
                    session, row.source_id, since(session, rule, row, state), row.captured_at, as_of
                )
                if held:  # stays armed: a gap-free re-observation confirms it
                    state["held"] = held
                else:
                    fire(session, rule, offer, state, row, value, as_of)
                    state["armed"] = False
            elif level is False:
                state["armed"] = True
            if rule.type not in PCT:  # stock compares with the last state, not the first
                state["ref"], state["ref_at"] = value, at
            state["value"], state["at"] = value, at
        elif "held" in state and rule.type != "freight_change" and seen(session, row, as_of):
            fire(session, rule, offer, state, row, value, as_of)
            state["armed"] = False
            del state["held"]
        if "held" in state:
            status, skipped = "skipped", state["held"]
    return settle(rule, status, entities, skipped, as_of)


def settle(
    rule: AlertRule,
    status: str,
    entities: dict[str, dict[str, Any]],
    skipped: dict[str, str] | None,
    as_of: datetime,
) -> str:
    rule.last_value = {"status": status, "entities": entities} | (
        {"skipped": skipped} if skipped else {}
    )
    rule.armed = all(state.get("armed", True) for state in entities.values())
    rule.last_evaluated_at = as_of
    return status


def midnight(day: date) -> datetime:
    return datetime.combine(day, time(), UTC)


def watched(session: Session, rule: AlertRule) -> list[UUID]:
    """A score rule's products: its product or the watchlist's items now, each as its survivor
    through any chain of merges (DEC-263)."""
    ids: Any = [UUID(str(rule.target_id))]
    if rule.target_type == "watchlist":
        ids = select(WatchlistItem.product_id).where(
            WatchlistItem.workspace_id == rule.workspace_id,
            WatchlistItem.watchlist_id == UUID(str(rule.target_id)),
        )
    tree = select(Product.id, Product.merged_into_id).where(Product.id.in_(ids)).cte(recursive=True)
    tree = tree.union(
        select(Product.id, Product.merged_into_id).join(tree, Product.id == tree.c.merged_into_id)
    )
    return list(session.scalars(select(tree.c.id).where(tree.c.merged_into_id.is_(None))))


def reading(
    session: Session, rule: AlertRule, row: Score, as_of: datetime
) -> tuple[Any, Any, dict[str, str] | None, str | None]:
    """(value, reference, gap, source) of a stored row. Saturation: its value. Velocity: the
    Lifecycle row's V7(t) and V7(t-7) in its primary family (DEC-326), and a gap in either
    window: one detected before `as_of` from t-14 to the cutoff, else a flagged window (a kept
    value's `gap`, DEC-310). A NULL is None: no source, never 0."""
    parts = row.explanation["components"]
    source = next((c["source"] for c in parts if c["source"] and not c["missing"]), None)
    if rule.type == "saturation_cross":
        return None if row.value is None else float(row.value), None, None, source
    if not parts:
        return None, None, None, None
    family, t, week = parts[0]["family"], row.date, timedelta(days=7)
    named = {c["name"]: c for c in parts}
    now, prev = named[f"{family}_v7"], named[f"{family}_v7_prev"]
    held = None
    source_id = session.scalar(select(Source.id).where(Source.key == now["source"]))
    if source_id is not None:
        held = gap(session, source_id, midnight(t - 2 * week), midnight(t + timedelta(1)), as_of)
    windows = [(t - 2 * week, t - week, prev), (t - week, t, now)]
    flagged = [(start, end) for start, end, c in windows if c["gap"] and c["raw"] is not None]
    if held is None and flagged:
        held = {"reason": "gap", "from": str(flagged[0][0]), "to": str(flagged[-1][1])}
    value = None if prev["raw"] is None else now["raw"]
    return value, prev["raw"], held, now["source"]


def fire_score(
    session: Session,
    rule: AlertRule,
    row: Score,
    old: dict[str, Any],
    value: Any,
    source: str | None,
    as_of: datetime,
) -> None:
    at = midnight(row.date + timedelta(days=1)).isoformat()  # the row's cutoff (DEC-031)
    spike = rule.type == "velocity_spike"
    payload = {
        "old": old,
        "new": {"value": value, "as_of": at, "source": source, "model_version": row.model_version},
        "threshold": SPIKE | rule.params if spike else dict(rule.params),
        "as_of": {source or "scores": at},
        "link": f"/products/{row.product_id}" + ("/trends" if spike else ""),
    }
    session.execute(
        insert(Alert)
        .values(
            workspace_id=rule.workspace_id,
            rule_id=rule.id,
            type=rule.type,
            entity_type="product",
            entity_id=str(row.product_id),
            dedupe_key=f"{rule.id}:product:{row.product_id}:{row.date}",
            fired_at=as_of,
            payload=payload,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
    )


def scored(session: Session, rule: AlertRule, as_of: datetime) -> str:
    """Advance each watched product from its newest stored row dated before `as_of`'s day: a
    day d row holds only captures before d+1 00:00Z (DEC-031), and SC-6 writes it after that.
    A new model_version is a new reference, so two versions are never compared."""
    before = (rule.last_value or {}).get("entities", {})
    entities: dict[str, dict[str, Any]] = {}
    status, skipped = "no_source", None
    rows = session.scalars(
        latest_scores(cast(Any, SCORED[rule.type])).where(
            Score.product_id.in_(watched(session, rule)),
            Score.date < as_of.astimezone(UTC).date(),
        )
    )
    for row in rows:
        key, day = f"product:{row.product_id}", str(row.date)
        at = midnight(row.date + timedelta(days=1)).isoformat()
        state = before.get(key)
        value, ref, held, source = reading(session, rule, row, as_of)
        if state is not None and state["date"] == day:  # nothing new since the last evaluation
            entities[key] = state
        elif held:  # gap-suppressed (vault Firing semantics): no alert, and the state stays
            entities[key] = (state or {}) | {"date": day, "held": held}
        elif value is None:  # no score: no source, never a crossing from 0
            if state is not None:
                entities[key] = state
            continue
        elif state is None or state.get("version") != row.model_version:  # the reference
            armed = past(rule, ref, value) is not True
            entities[key] = {"value": value, "at": at, "date": day,
                             "version": row.model_version, "armed": armed}  # fmt: skip
        else:
            state = {name: v for name, v in state.items() if name != "held"}
            level = past(rule, ref, value)
            if state["armed"] and level:
                old = {"value": state["value"], "as_of": state["at"]}
                if ref is not None:  # velocity: V7(t-7), at t-7's cutoff
                    then = midnight(row.date - timedelta(days=6)).isoformat()
                    old = {"value": ref, "as_of": then}
                fire_score(session, rule, row, old, value, source, as_of)
                state["armed"] = False
            elif level is False:
                state["armed"] = True
            entities[key] = state | {"value": value, "at": at, "date": day}
        status = "ok" if status == "no_source" else status
        if "held" in entities[key]:
            status, skipped = "skipped", entities[key]["held"]
    return settle(rule, status, entities, skipped, as_of)


def evaluate(session: Session, workspace_id: UUID, as_of: datetime) -> dict[UUID, str]:
    """Evaluate the workspace's enabled, unmuted rules at `as_of`. Returns each rule's status:
    ok, no_source (nothing it watches has data yet) or skipped (a gap held back a crossing)."""
    mine = AlertRule.workspace_id == workspace_id
    tests = select(ProductTest.id).where(
        ProductTest.workspace_id == workspace_id, ProductTest.stage.in_(OPEN)
    )
    if session.scalar(tests.exists().select()):
        have = set(
            session.scalars(select(AlertRule.type).where(mine, AlertRule.target_type == "test"))
        )
        session.add_all(
            AlertRule(
                workspace_id=workspace_id, name=name, type=kind, target_type="test", params=params
            )
            for name, kind, params in TESTING
            if kind not in have
        )
    rules = session.scalars(
        select(AlertRule)
        .where(mine, AlertRule.enabled, AlertRule.type.in_(TYPES))
        .where(or_(AlertRule.muted_until.is_(None), AlertRule.muted_until <= as_of))
        .order_by(AlertRule.created_at, AlertRule.id)
    ).all()
    statuses = {
        rule.id: (scored if rule.type in SCORED else step)(session, rule, as_of) for rule in rules
    }
    session.flush()
    return statuses
