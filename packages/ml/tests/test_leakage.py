"""Leakage test part (a), truncation invariance (vault Intelligence/Feature Store & Leakage Test).

Part (b), the backtest splitter's purge assertion, arrives with the Phase 6 harness.
"""

import ast
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

import pulso_ml.features
from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingVariant,
    MatchDecision,
    Product,
    RawPayload,
    Source,
    Store,
    Supplier,
    VariantSnapshot,
)
from pulso_ml.features.daily import compute, cutoff, run

START = date(2026, 9, 1)
P = {name: UUID(int=n) for n, name in enumerate(["p1", "p2", "p3", "p4", "p5", "p6", "p7"], 1)}
HOMES = {"L1": "p1", "L2": "p1", "L3": "p2", "L4": "p3", "L5": "p4"}  # one Shopify store
HOMES |= {"C1": "p1", "C2": "p5", "C3": "p6"}  # CJ
PERIOD = {"L1": 1, "L2": 2, "L3": 3, "L4": 5, "L5": 7}  # each sells one unit every n days


def on(i: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime.combine(START + timedelta(days=i), time(hour, minute), UTC)


def stock(variant: str, i: int) -> int:
    match variant:
        case "C1a":
            return 500 - 3 * i + (200 if i >= 20 else 0)  # a restock on day 20
        case "C1b":
            return 300 - i // 2  # unchanged every other day: no snapshot, still covered
        case "C2a":
            return 800 - 5 * i - (400 if i >= 25 else 0)  # an implausible drop on day 25
        case "C3a":
            return 400 - 2 * i - 6 * max(0, i - 35)  # selling faster from day 36
        case "C4a":
            return 90 - i
    return 300 - i // PERIOD[variant[:2]] - (3 if i >= 15 else 0)  # day 15: a store-wide sync


def build(session: Session) -> None:
    """45 days of CJ and Shopify stock, written as the collectors would have, then today's
    pointers. Each case the vault lists for demand features sits on a sample date below."""
    source = {key: id_ for key, id_ in session.execute(select(Source.key, Source.id))}
    store = Store(domain="store.example.test", platform="shopify")
    supplier = Supplier(platform="cj", external_id="cj", name="CJ Dropshipping")
    session.add_all([store, supplier, *(Product(id=id_, name=n) for n, id_ in P.items())])
    session.flush()
    listings: dict[str, Listing] = {}
    variants: dict[str, ListingVariant] = {}

    def link(name: str, product: str, at: datetime, **move: str) -> None:
        action, origin = move.get("action", "link"), move.get("origin")
        session.add(
            MatchDecision(
                actor="owner" if origin else "algo",
                action=action,
                listing_id=listings[name].id,
                from_product_id=P[origin] if origin else None,
                to_product_id=P[product],
                decided_at=at,
            )
        )
        listings[name].product_id = P[product]

    for name, product in [*HOMES.items(), ("C4", "p5")]:
        cj = name.startswith("C")
        listings[name] = Listing(
            source_id=source["cj" if cj else "shopify_stores"],
            external_id=name,
            url="https://example.test/p",
            title=name,
            **({"supplier_id": supplier.id} if cj else {"store_id": store.id}),
        )
        session.add(listings[name])
        session.flush()
        for suffix in ["a", "b"] if name == "C1" else ["a"]:
            row = ListingVariant(listing_id=listings[name].id, external_id=suffix)
            variants[name + suffix] = row
            session.add(row)
        if name != "C4":
            link(name, product, on(0))
    session.flush()
    # Day 40, stamped exactly at day 39's cutoff: P6 merges into P5 and L2 splits onto P7.
    link("C3", "p5", on(40), action="merge", origin="p6")
    link("L2", "p7", on(40), action="split", origin="p1")
    link("C4", "p5", on(40))  # first captured exactly at day 41's cutoff
    session.get_one(Product, P["p6"]).merged_into_id = P["p5"]

    last: dict[str, int] = {}
    for i in range(1, 46):
        for key, at, names in [
            # Day 41's CJ run is planned before midnight and fetched at it: it counts for day 42.
            ("cj", on(i) if i == 42 else on(i, 3), ["C1", "C2", "C3"] + ["C4"] * (i >= 42)),
            ("shopify_stores", on(i, 5), list(PERIOD)),
        ]:
            if i == 30 or (key == "cj" and i == 41) or (key != "cj" and 31 <= i <= 34):
                continue  # the PC was off: no run at all
            collector_run = CollectorRun(source_id=source[key], trigger="schedule")
            session.add(collector_run)
            session.flush()
            for name in names:
                payload = RawPayload(
                    source_id=source[key],
                    run_id=collector_run.id,
                    captured_at=at,
                    request={"endpoint": "/product/stock/getInventoryByPid"}
                    if key == "cj"
                    else {"path": f"/products/{name}.js"},
                    bytes=1,
                    sha256=f"{name}{i}".ljust(64, "0"),
                )
                session.add(payload)
                session.flush()
                failed = (name, i) == ("C3", 33)  # a partial run: this target failed
                if key == "cj" or name == names[-1]:  # Shopify's target is the whole store
                    session.add(
                        CollectorRunTarget(
                            run_id=collector_run.id,
                            scope="cj_tracked" if key == "cj" else "shopify_variants_js",
                            target_id=name if key == "cj" else store.domain,
                            status="failed" if failed else "success",
                            raw_payload_id=None if failed else payload.id,
                            captured_at=at - timedelta(seconds=30),
                        )
                    )
                for variant in [v for v in variants if v.startswith(name)]:
                    level = stock(variant, i)
                    if failed or last.get(variant) == level:
                        continue  # change-only snapshots: an unchanged level writes no row
                    last[variant] = level
                    late = (variant, i) == ("C2a", 22)  # captured 2 days after it describes
                    session.add(
                        VariantSnapshot(
                            variant_id=variants[variant].id,
                            captured_at=at,
                            observed_for=(at - timedelta(days=2 if late else 0)).date(),
                            raw_payload_id=payload.id,
                            values_hash=str(level),
                            currency="USD",
                            inventory_quantity=level,
                            inventory_management="shopify" if key != "cj" else None,
                            # L3's store lets it oversell from day 36: its level means nothing.
                            inventory_policy=None
                            if key == "cj"
                            else "continue"
                            if variant == "L3a" and i >= 36
                            else "deny",
                        )
                    )
    session.flush()


TRUNCATE = [
    "ALTER TABLE match_decisions DISABLE TRIGGER match_decisions_append_only",
    "DELETE FROM match_decisions WHERE decided_at >= :cutoff",
    """UPDATE collector_run_targets SET status = 'pending', raw_payload_id = NULL
       WHERE raw_payload_id IN (SELECT id FROM raw_payloads WHERE captured_at >= :cutoff)""",
    "DELETE FROM collector_run_targets WHERE captured_at >= :cutoff",
    "DELETE FROM variant_snapshots WHERE captured_at >= :cutoff",
    "DELETE FROM listing_snapshots WHERE captured_at >= :cutoff",
    "DELETE FROM raw_payloads WHERE captured_at >= :cutoff",
    # Today's pointers hold later merges and splits; nothing knew them then.
    "UPDATE listings SET product_id = NULL",
    "UPDATE products SET merged_into_id = NULL",
]


@pytest.mark.db
def test_features_equal_those_from_a_copy_truncated_at_the_cutoff(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        build(session)
        for i in [15, 20, 29, 33, 36, 39, 40, 41, 45]:
            day = START + timedelta(days=i)
            full = compute(session, day)
            truncated = session.begin_nested()
            for statement in TRUNCATE:
                session.execute(text(statement), {"cutoff": cutoff(day)})
            assert compute(session, day) == full, day
            truncated.rollback()


@pytest.mark.db
def test_membership_follows_the_decisions_known_at_the_cutoff(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        build(session)
        sync = {(f.product_id, f.family): f for f in compute(session, START + timedelta(20))}
        before = {(f.product_id, f.family): f for f in compute(session, START + timedelta(39))}
        after = {(f.product_id, f.family): f for f in compute(session, START + timedelta(45))}
    # Day 15's crawl dropped all 5 of the store's listings: a sync, so it adds nothing.
    assert sync[P["p1"], "shp_inv"].velocity_7d == 6 + 4  # L1 and L2 over days 14 to 20
    assert (P["p6"], "cj_stock") in before and (P["p7"], "shp_inv") not in before
    assert (P["p6"], "cj_stock") not in after
    assert after[P["p1"], "shp_inv"].velocity_7d == 7 and after[P["p7"], "shp_inv"].velocity_7d == 3
    assert after[P["p1"], "shp_inv"].growth_7d is None  # t−14 fell in the Shopify outage
    assert after[P["p2"], "shp_inv"][4:] == (None, None, Decimal(0), True)  # unknown, not 0
    cj = after[P["p5"], "cj_stock"]
    assert cj.growth_7d is not None and cj.has_gap  # no CJ evidence on day 41
    assert cj.coverage == Decimal("0.75")  # C2 and C3 7 of 8 days, C4 (new) 4: 18 of 24


@pytest.mark.db
def test_rerunning_a_day_writes_nothing_and_a_new_version_appends(db_engine: Engine) -> None:
    day = START + timedelta(days=33)
    xmin = text(
        "SELECT product_id, family, feature_version, xmin::text FROM product_daily_features"
    )
    with Session(db_engine) as session:
        build(session)
        written = run(session, day)
        session.commit()
        rows = {(r.product_id, r.family): r for r in compute(session, day)}
        first = session.execute(xmin).all()
        assert run(session, day) == 0
        session.commit()
        assert session.execute(xmin).all() == first
        assert run(session, day, version="999-test") == written
    assert written == len(rows) == 7  # P1 twice, P2..P6 once; P7 has no listing yet
    assert all(r.velocity_7d is None and r.has_gap for (_, f), r in rows.items() if f == "shp_inv")
    cj = rows[P["p5"], "cj_stock"]
    assert cj.velocity_7d is not None and cj.has_gap  # day 30 missed: within tolerance
    assert rows[P["p6"], "cj_stock"].velocity_7d is None  # its target failed today


def test_only_the_repository_imports_table_models() -> None:
    for path in Path(pulso_ml.features.__file__).parent.glob("*.py"):
        modules = {
            node.module or ""
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
        }
        tables = {m for m in modules if m.startswith(("pulso_core.models", "pulso_ml.matching"))}
        assert path.name == "repository.py" or not tables, path.name
