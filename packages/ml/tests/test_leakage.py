"""Leakage test part (a), truncation invariance (vault Intelligence/Feature Store & Leakage Test).

Part (b), the backtest splitter's purge assertion, arrives with the Phase 6 harness.
"""

import ast
import math
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

import pulso_ml.features
from pulso_core.models import (
    CollectionGap,
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingVariant,
    MatchDecision,
    Product,
    ProductKeyword,
    RawPayload,
    SearchTrend,
    Source,
    Store,
    Supplier,
    User,
    VariantSnapshot,
    Workspace,
)
from pulso_ml.features.daily import compute, cutoff, run

START = date(2026, 9, 1)
P = {name: UUID(int=n) for n, name in enumerate(["p1", "p2", "p3", "p4", "p5", "p6", "p7"], 1)}
HOMES = {"L1": "p1", "L2": "p1", "L3": "p2", "L4": "p3", "L5": "p4", "L6": "p4"}  # one store
HOMES |= {"C1": "p1", "C2": "p5", "C3": "p6"}  # CJ
PERIOD = {"L1": 1, "L2": 2, "L3": 3, "L4": 5, "L5": 7, "L6": 1}  # one unit every n days


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
                    # Day 17's C1a capture was misread by parser 0, then re-parsed by parser 1.
                    for parser, read in [("0", level - 20)] * ((variant, i) == ("C1a", 17)) + [
                        ("1", level)
                    ]:
                        session.add(
                            VariantSnapshot(
                                variant_id=variants[variant].id,
                                captured_at=at,
                                observed_for=(at - timedelta(days=2 if late else 0)).date(),
                                raw_payload_id=payload.id,
                                parser_version=parser,
                                values_hash=str(read),
                                currency="USD",
                                inventory_quantity=read,
                                inventory_management="shopify" if key != "cj" else None,
                                # Overselling L6, and L3 from day 36: their level means nothing.
                                inventory_policy=None
                                if key == "cj"
                                else "continue"
                                if variant == "L6a" or (variant == "L3a" and i >= 36)
                                else "deny",
                            )
                        )
                        session.flush()  # ids follow the parses' order
    session.flush()


def interest(capture: int, day: int) -> int:
    """Each Trends capture scales by its own window's peak: day 18's spike, inside every capture
    from day 20 on, rescales them against day 13's."""

    def raw(d: int) -> int:
        return 200 if d == 18 else 20 + max(0, d)

    return round(100 * raw(day) / max(raw(d) for d in range(capture - 89, capture + 1)))


def sell(session: Session, store: Store, name: str, product: str, seen: datetime) -> Listing:
    """A store listing first seen at `seen` and linked to the product then."""
    shopify = session.scalars(select(Source.id).where(Source.key == "shopify_stores")).one()
    listing = Listing(
        source_id=shopify,
        external_id=name,
        url="https://example.test/p",
        title=name,
        store_id=store.id,
        first_seen_at=seen,
    )
    session.add(listing)
    session.flush()
    session.add(
        MatchDecision(
            actor="algo",
            action="link",
            listing_id=listing.id,
            to_product_id=P[product],
            decided_at=seen,
        )
    )
    return listing


def build_inputs(session: Session) -> None:
    """Non-demand inputs over build()'s days (DEC-311): confirmed keywords, Monday Trends captures
    and a day-45 CSV backfill, store listings for sellers, and Data Health's missed slots."""
    source = {key: id_ for key, id_ in session.execute(select(Source.key, Source.id))}
    workspace, user = Workspace(name="w"), User(clerk_user_id="u")
    session.add_all([workspace, user])
    session.flush()
    keywords = [("p1", "sunset lamp", 0), ("p6", "sunset lamp", 25), ("p3", "dog bed", 44)]
    for product, keyword, i in keywords:
        session.add(
            ProductKeyword(
                workspace_id=workspace.id,
                product_id=P[product],
                keyword=keyword,
                source="manual",
                status="confirmed",
                decided_by=user.id,
                decided_at=on(i),
            )
        )

    def capture(key: str, at: datetime) -> RawPayload:
        collector_run = CollectorRun(source_id=source[key], trigger="schedule")
        session.add(collector_run)
        session.flush()
        payload = RawPayload(
            source_id=source[key],
            run_id=collector_run.id,
            captured_at=at,
            request={},
            bytes=1,
            sha256=f"{key}{at:%j%H}".ljust(64, "0"),
        )
        session.add(payload)
        session.flush()
        return payload

    def trend(payload: RawPayload, keyword: str, i: int, value: int, window: str) -> None:
        session.add(
            SearchTrend(
                source_id=payload.source_id,
                raw_payload_id=payload.id,
                captured_at=payload.captured_at,
                observed_for=START + timedelta(days=i),
                keyword=keyword,
                geo="US",
                window=window,
                granularity="day",
                metric="relative_interest",
                value=value,
                is_partial=START + timedelta(days=i) == payload.captured_at.date(),  # today's
            )
        )

    for i in [13, 20, 41]:  # Mondays; 27 and 34 were missed
        payload = capture("google_trends", on(i, 9))
        for d in range(i - 89, i):
            trend(payload, "Sunset  Lamp", d, interest(i, d), "today 3-m")  # the seed's spelling
        trend(payload, "Sunset  Lamp", i, 100, "today 3-m")
    backfill = capture("google_trends", on(45, 12))  # the owner's CSV, describing past days
    for d in range(1, 31):
        trend(backfill, "sunset lamp", d, 50, "manual")  # not 12 weeks: day 41's capture stays
    for d in range(-55, 31):
        trend(backfill, "dog bed", d, 60 if d > 2 else 40, "manual")

    stores = [Store(domain=f"s{n}.example.test", platform="shopify") for n in range(4)]
    for store, i in zip(stores, [-60, -60, 10, 45], strict=True):
        store.first_seen_at = on(i, 12)
    session.add_all(stores)
    session.flush()
    sell(session, stores[0], "S0", "p1", on(-30, 12))
    sell(session, stores[1], "S1", "p1", on(20, 12))  # a panel store starts selling P1
    sell(session, stores[1], "S2", "p2", on(-30, 12)).delisted_at = on(38)  # a complete crawl
    sell(session, stores[2], "S3", "p1", on(10, 12))  # its store joins the panel on day 38
    sell(session, stores[3], "S4", "p1", on(45, 12))  # from the day-45 CSV import
    for key, days in [("cj", [30]), ("shopify_stores", range(30, 35)), ("google_trends", [27, 34])]:
        for i in days:
            session.add(
                CollectionGap(
                    source_id=source[key],
                    slot_key=f"{key}:{i}",
                    slot_start=on(i),
                    slot_end=on(i + 1),
                    reason="host_offline",
                    detected_at=on(i + 1, 0, 5),  # the audit on wake
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
    "DELETE FROM search_trends WHERE captured_at >= :cutoff",
    "DELETE FROM collection_gaps WHERE detected_at >= :cutoff",
    "ALTER TABLE product_keywords DISABLE TRIGGER product_keywords_no_delete",
    "DELETE FROM product_keywords WHERE decided_at >= :cutoff",
    "UPDATE listings SET delisted_at = NULL WHERE delisted_at >= :cutoff",
    "DELETE FROM raw_payloads WHERE captured_at >= :cutoff",
    # Today's pointers hold later merges and splits; nothing knew them then.
    "UPDATE listings SET product_id = NULL",
    "UPDATE products SET merged_into_id = NULL",
]


@pytest.mark.db
def test_features_equal_those_from_a_copy_truncated_at_the_cutoff(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        build(session)
        build_inputs(session)
        for i in [15, 20, 29, 30, 33, 36, 39, 40, 41, 44, 45]:
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
    # C1a sells 3 a day but restocks on day 20, C1b sells 4; day 17's misread is superseded.
    assert sync[P["p1"], "cj_stock"].velocity_7d == 6 * 3 + 4
    assert (P["p6"], "cj_stock") in before and (P["p7"], "shp_inv") not in before
    assert (P["p6"], "cj_stock") not in after
    assert after[P["p1"], "shp_inv"].velocity_7d == 7 and after[P["p7"], "shp_inv"].velocity_7d == 3
    assert after[P["p1"], "shp_inv"].growth_7d is None  # t−14 fell in the Shopify outage
    assert after[P["p2"], "shp_inv"][4:8] == (None, None, Decimal(0), True)  # unknown, not 0
    assert after[P["p4"], "shp_inv"].coverage == 1  # L6 never showed a level: not tracked
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


def r18(values: list[int]) -> float:
    """R-18 by hand over 84 daily values, oldest first."""
    return math.log((sum(values[56:]) / 28 + 1) / (sum(values[:56]) / 56 + 1))


def slope(capture: int) -> float:
    """A capture's slope: its complete days end the day before it."""
    return r18([interest(capture, d) for d in range(capture - 84, capture)])


@pytest.mark.db
def test_search_slope_reads_one_capture_without_its_partial_point(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        build(session)
        build_inputs(session)
        rows = {
            (i, f.product_id): f.features
            for i in [15, 20, 39, 40, 41, 44, 45]
            for f in compute(session, START + timedelta(days=i))
            if f.family == "gt_interest"
        }
    p1 = {i: rows[i, P["p1"]] for i in [15, 20, 39, 41, 45]}
    assert p1[15]["gt_slope"] == pytest.approx(slope(13))
    # Day 18's spike rescales day 20's capture: it stands alone, never stitched onto day 13's.
    stitched = r18([interest(13, d) if d < 13 else interest(20, d) for d in range(-64, 20)])
    assert p1[20]["gt_slope"] == pytest.approx(slope(20)) != pytest.approx(slope(13))
    assert p1[20]["gt_slope"] != pytest.approx(stitched)
    assert p1[39] == p1[20] == rows[39, P["p6"]]  # the Mondays between were missed
    assert (20, P["p6"]) not in rows  # its keyword is confirmed on day 25
    assert (40, P["p6"]) not in rows  # merged into P5 on day 40
    assert p1[41]["gt_slope"] == pytest.approx(slope(41))
    # The day-45 CSV holds only 30 days of P1's keyword, so day 41's capture still counts. P3's
    # keyword, confirmed on day 44, has its first capture in that CSV.
    assert p1[45] == p1[41] and (44, P["p3"]) not in rows
    assert rows[45, P["p3"]] == {
        "gt_slope": pytest.approx(math.log(61 / 41)),
        "gt_keywords": 1,
        "gt_as_of": on(45, 12).isoformat(),
    }


@pytest.mark.db
def test_seller_growth_holds_its_panel_while_the_level_counts_every_store(
    db_engine: Engine,
) -> None:
    def inputs(level: int, now: int, then: int, panel: int) -> dict[str, object]:
        growth = pytest.approx(math.log((now + 1) / (then + 1)))
        return {"shp_sellers": level, "shp_seller_g28": growth, "panel_size": panel}

    with Session(db_engine) as session:
        build(session)
        build_inputs(session)

        coverage: dict[int, set[Decimal]] = {}

        def sellers(i: int) -> dict[UUID, object]:
            rows = compute(session, START + timedelta(days=i))
            coverage[i] = {f.coverage for f in rows if f.family == "shp_sellers"}
            return {f.product_id: f.features for f in rows if f.family == "shp_sellers"}

        assert sellers(15) == {P["p1"]: inputs(2, 1, 1, 2), P["p2"]: inputs(1, 1, 1, 2)}
        # S1 joins in a panel store; S3's store isn't 28 days old yet; S2 is delisted on day 38.
        assert sellers(36) == {P["p1"]: inputs(3, 2, 1, 2), P["p2"]: inputs(1, 1, 1, 2)}
        assert sellers(39) == {P["p1"]: inputs(3, 3, 2, 3), P["p2"]: inputs(0, 0, 1, 3)}
        assert coverage[39] == {1}  # the panel holds every store tracked by then
        before = sellers(45)
        assert before[P["p1"]] == inputs(4, 3, 2, 3)  # S4's store, imported today, isn't in it
        assert coverage[45] == {Decimal("0.75")}
        for n in range(10):  # a batch of newly tracked stores, each already selling P1
            store = Store(domain=f"new{n}.example.test", platform="shopify")
            store.first_seen_at = on(45, 13)
            session.add(store)
            session.flush()
            sell(session, store, f"N{n}", "p1", on(45, 13))
        after = sellers(45)
    assert after == {P["p1"]: {**inputs(4, 3, 2, 3), "shp_sellers": 14}, P["p2"]: before[P["p2"]]}
    assert coverage[45] == {Decimal("0.2143")}  # 3 of 14 tracked stores


SOURCES = {"cj_stock": "cj", "shp_inv": "shopify_stores"}
SOURCES |= {"gt_interest": "google_trends", "shp_sellers": "shopify_stores"}


@pytest.mark.db
def test_gap_flags_list_data_healths_gap_days(db_engine: Engine) -> None:
    health = text(
        "SELECT s.key, c.day FROM source_daily_coverage c JOIN sources s ON s.id = c.source_id "
        "WHERE c.status = 'gap' ORDER BY c.day"
    )
    with Session(db_engine) as session:
        build(session)
        build_inputs(session)
        gaps: dict[str, list[date]] = defaultdict(list)
        for key, day in session.execute(health):
            gaps[key].append(day)
        day30, day45, day59 = (compute(session, START + timedelta(days=i)) for i in [30, 45, 59])
    days = {key: [(d - START).days for d in found] for key, found in gaps.items()}
    assert days == {"cj": [30], "shopify_stores": [30, 31, 32, 33, 34], "google_trends": [27, 34]}
    assert {f.family for f in day45} == set(SOURCES)
    for f in day45:  # t−28..t is days 17..45
        expected = [d.isoformat() for d in gaps[SOURCES[f.family]] if d >= START + timedelta(17)]
        assert f.gap_flags == {"missed_runs": expected}, f.family
    # The audit found day 30's missed slots on waking, after day 30's cutoff.
    trends = [(START + timedelta(27)).isoformat()]
    assert all(
        f.gap_flags["missed_runs"] == (trends if f.family == "gt_interest" else []) for f in day30
    )
    first = {f.family: f.gap_flags["missed_runs"][:1] for f in day59}  # days 31..59 only
    assert first == {"shp_inv": ["2026-10-02"], "gt_interest": ["2026-10-05"]} | {
        "shp_sellers": ["2026-10-02"],
        "cj_stock": [],
    }
