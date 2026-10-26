from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.alerts import evaluate
from pulso_core.models import (
    Alert,
    AlertRule,
    CollectionGap,
    Product,
    Watchlist,
    WatchlistItem,
    Workspace,
)
from pulso_core.scores import Component, Explanation, ScoreRow, write

# Score rules (DEC-353): velocity_spike and saturation_cross from SC-6's stored rows, crossing,
# hysteresis, dedupe, the velocity gap suppression, no source and watchlist targets.

CJ = 2  # seeded source id, key "cj"
D0 = date(2026, 11, 2)


def day(n: int) -> date:
    return D0 + timedelta(days=n)


def cutoff(n: int) -> datetime:  # as_of for day n: d+1 00:00Z, as SC-6's nightly call passes it
    return datetime.combine(day(n + 1), datetime.min.time(), UTC)


def part(name: str, raw: float | None, gap: bool = False, family: str = "cj_stock") -> Component:
    source = "cj" if family == "cj_stock" else "shopify_stores"
    return Component(name=name, family=family, source=source, weight=0, raw=raw,
                     missing=raw is None, gap=gap)  # fmt: skip


def explained(version: str, components: tuple[Component, ...]) -> Explanation:
    missing = tuple(c.name for c in components if c.missing)
    return Explanation(model_version=version, config_digest="d", components=components,
                       missing=missing, coverage=1 - len(missing) / len(components))  # fmt: skip


def velocity(
    session: Session,
    product: UUID,
    n: int,
    v7: float | None,
    prev: float | None,
    gaps: tuple[bool, bool] = (False, False),
    family: str = "cj_stock",
) -> None:
    """Day n's Lifecycle row as SC-6 writes it: V7(t) and V7(t-7) in its primary family."""
    components = (
        part(f"{family}_v7", v7, gaps[0], family),
        part(f"{family}_v7_prev", prev, gaps[1], family),
        part(f"{family}_g7", None, family=family),
    )
    row = ScoreRow(product, day(n), "lifecycle", None, explained("000-life", components))
    write(session, [row])


def saturation(
    session: Session, product: UUID, n: int, value: float | None, version: str = "000-sat"
) -> None:
    components = (part("shp_sellers", None if value is None else 2.0, family="shp_sellers"),)
    row = ScoreRow(product, day(n), "saturation", value, explained(version, components))
    write(session, [row])


def setup(session: Session) -> tuple[UUID, UUID]:
    ws = Workspace(name="Workspace")
    product = Product(name="Sunset lamp")
    session.add_all([ws, product])
    session.flush()
    return ws.id, product.id


def rule(session: Session, ws: UUID, kind: str, target: tuple[str, object], **params: Any) -> UUID:
    row = AlertRule(workspace_id=ws, name=kind, type=kind, target_type=target[0],
                    target_id=str(target[1]), params=params)  # fmt: skip
    session.add(row)
    session.flush()
    return row.id


def alerts(session: Session, rule_id: UUID) -> list[Alert]:
    return list(session.scalars(select(Alert).where(Alert.rule_id == rule_id).order_by(Alert.id)))


@pytest.mark.db
def test_a_velocity_spike_fires_once_and_again_only_after_falling_back(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, product = setup(session)
        spike = rule(session, ws, "velocity_spike", ("product", product))
        nights = [(20, 20), (30, 20), (31, 21), (34, 21), (24, 20), (10, 24), (40, 24)]
        # +0% the reference, exactly +50% fires, +47.6% inside the 47.5% band, +62% stays fired, +20%
        # re-arms, -58% is a fall, not a spike, +67% fires again
        fired = []
        for n, (v7, prev) in enumerate(nights):
            velocity(session, product, n, v7, prev)
            assert evaluate(session, ws, cutoff(n)) == {spike: "ok"}
            fired.append(len(alerts(session, spike)))
        assert fired == [0, 1, 1, 1, 1, 1, 2]
        first, second = alerts(session, spike)
        assert (first.type, first.entity_type, first.entity_id) == (
            "velocity_spike",
            "product",
            str(product),
        )
        assert first.dedupe_key == f"{spike}:product:{product}:2026-11-03"
        assert first.fired_at == cutoff(1)
        assert first.payload == {
            "old": {"value": 20, "as_of": "2026-10-28T00:00:00+00:00"},
            "new": {
                "value": 30,
                "as_of": "2026-11-04T00:00:00+00:00",
                "source": "cj",
                "model_version": "000-life",
            },
            "threshold": {"pct": 50, "window_days": 7, "min_volume": 10},
            "as_of": {"cj": "2026-11-04T00:00:00+00:00"},
            "link": f"/products/{product}/trends",
            "product": "Sunset lamp",
        }
        assert (second.dedupe_key[-10:], second.payload["old"]["value"]) == ("2026-11-08", 24)
        evaluate(session, ws, cutoff(6))  # a re-run fires nothing new
        session.get_one(AlertRule, spike).last_value = None  # nor does a reset state's re-run
        evaluate(session, ws, cutoff(6))
        evaluate(session, ws, cutoff(6) + timedelta(hours=6))
        assert len(alerts(session, spike)) == 2


@pytest.mark.db
def test_a_velocity_spike_needs_its_volume_floor_and_a_prior_week(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, product = setup(session)
        spike = rule(session, ws, "velocity_spike", ("product", product), pct=50, min_volume=12)
        velocity(session, product, 0, 4, None)  # no V7(t-7) yet: nothing to compare
        assert evaluate(session, ws, cutoff(0)) == {spike: "no_source"}
        for n, (v7, prev) in enumerate([(4, 4), (8, 4), (11.9, 4), (12, 4), (14, 0)], start=1):
            velocity(session, product, n, v7, prev)  # a prior week of 0 reads as 1
            evaluate(session, ws, cutoff(n))
            if n < 4:  # +100% and +197.5% under 12 units/7d: no alert
                assert alerts(session, spike) == []
        [alert] = alerts(session, spike)
        assert alert.dedupe_key.endswith(":2026-11-06")
        assert alert.payload["threshold"] == {"pct": 50, "window_days": 7, "min_volume": 12}
        fresh = Product(name="Fan")
        session.add(fresh)
        session.flush()
        spike = rule(session, ws, "velocity_spike", ("product", fresh.id))
        for n, (v7, prev) in enumerate([(40, 20), (44, 20)], start=10):  # a first sight past it
            velocity(session, fresh.id, n, v7, prev)
            evaluate(session, ws, cutoff(n))
        assert alerts(session, spike) == []  # is the reference, not a crossing


@pytest.mark.db
def test_a_gap_in_either_window_skips_a_velocity_spike(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, product = setup(session)
        spike = rule(session, ws, "velocity_spike", ("product", product))
        velocity(session, product, 0, 20, 20)
        evaluate(session, ws, cutoff(0))
        hole = (cutoff(0) - timedelta(days=12), cutoff(0) - timedelta(days=11))  # in t-14..t-7
        session.add(CollectionGap(source_id=CJ, slot_key="k1", slot_start=hole[0], slot_end=hole[1],
                                  reason="missed", detected_at=cutoff(0)))  # fmt: skip
        late = CollectionGap(source_id=CJ, slot_key="k2", slot_start=cutoff(0),
                             slot_end=cutoff(0) + timedelta(hours=6), reason="missed",
                             detected_at=cutoff(1))  # fmt: skip
        session.add(late)  # detected at as_of: not read
        velocity(session, product, 1, 32, 20)  # +60% over the gap
        assert evaluate(session, ws, cutoff(1)) == {spike: "skipped"}
        span = {"reason": "gap", "from": hole[0].isoformat(), "to": hole[1].isoformat()}
        stored = session.get_one(AlertRule, spike).last_value
        assert stored is not None and stored["skipped"] == span
        assert evaluate(session, ws, cutoff(1)) == {spike: "skipped"}  # a re-run stays skipped
        assert alerts(session, spike) == []
        velocity(session, product, 16, 35, 21)  # both gaps left the windows: still armed, fires
        assert evaluate(session, ws, cutoff(16)) == {spike: "ok"}
        [alert] = alerts(session, spike)
        assert alert.dedupe_key.endswith(":2026-11-18")
        stored = session.get_one(AlertRule, spike).last_value
        assert stored is not None and "skipped" not in stored
        velocity(session, product, 17, 21, 21)  # re-arms
        today = cutoff(17) + timedelta(hours=6)  # a gap on day t itself
        session.add(CollectionGap(source_id=CJ, slot_key="k3", slot_start=today,
                                  slot_end=today + timedelta(hours=1), reason="missed",
                                  detected_at=today + timedelta(hours=2)))  # fmt: skip
        velocity(session, product, 18, 42, 21)
        evaluate(session, ws, cutoff(17))
        assert evaluate(session, ws, cutoff(18)) == {spike: "skipped"}
        assert len(alerts(session, spike)) == 1


@pytest.mark.db
def test_a_flagged_window_skips_a_velocity_spike_with_that_window(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, product = setup(session)
        spike = rule(session, ws, "velocity_spike", ("product", product))
        family = "shp_inv"  # its source has no collection gap here
        velocity(session, product, 0, 20, 20, (True, False), family)  # a first sight over a gap
        assert evaluate(session, ws, cutoff(0)) == {spike: "skipped"}
        assert session.get_one(AlertRule, spike).armed
        velocity(session, product, 1, 20, 20, family=family)  # the reference
        assert evaluate(session, ws, cutoff(1)) == {spike: "ok"}
        spans = []
        for n, gaps in ((2, (True, False)), (3, (False, True)), (4, (True, True))):
            velocity(session, product, n, 34, 21, gaps, family)  # kept values, flagged (DEC-310)
            assert evaluate(session, ws, cutoff(n)) == {spike: "skipped"}
            stored = session.get_one(AlertRule, spike).last_value
            assert stored is not None
            spans.append((stored["skipped"]["from"], stored["skipped"]["to"]))
        assert spans == [
            ("2026-10-28", "2026-11-04"),  # t-7..t
            ("2026-10-22", "2026-10-29"),  # t-14..t-7
            ("2026-10-23", "2026-11-06"),
        ]
        velocity(session, product, 5, 34, None, (False, True), family)  # a NULL's flag: no value
        assert evaluate(session, ws, cutoff(5)) == {spike: "no_source"}
        assert alerts(session, spike) == []
        velocity(session, product, 6, 34, 21, family=family)  # the NULL kept the armed state
        evaluate(session, ws, cutoff(6))
        assert len(alerts(session, spike)) == 1


@pytest.mark.db
def test_saturation_crosses_fire_once_each_way_and_a_null_is_no_source(db_engine: Engine) -> None:
    with Session(db_engine) as session:
        ws, product = setup(session)
        up = rule(session, ws, "saturation_cross", ("product", product), threshold=65,
                  direction="above")  # fmt: skip
        down = rule(session, ws, "saturation_cross", ("product", product), threshold=35,
                    direction="below")  # fmt: skip
        saturation(session, product, 0, None)  # a NULL row: no source, never 0
        assert evaluate(session, ws, cutoff(0)) == {up: "no_source", down: "no_source"}
        values = [36.7, 66, 62, 70, 34, 36, 33, 60, 65, 30]
        # up: 36.7 the reference, 66 fires, 62 inside 61.75..65, 70 stays fired, 34 re-arms, 65
        # fires again; down: 36.7 inside 35..36.75 (armed), 34 fires, 36 inside, 33 stays fired,
        # 60 re-arms, 30 fires again
        for n, value in enumerate(values, start=1):
            saturation(session, product, n, value)
            evaluate(session, ws, cutoff(n))
        assert [a.dedupe_key[-10:] for a in alerts(session, up)] == ["2026-11-04", "2026-11-11"]
        assert [a.dedupe_key[-10:] for a in alerts(session, down)] == ["2026-11-07", "2026-11-12"]
        first = alerts(session, up)[0]
        assert first.payload["old"] == {"value": 36.7, "as_of": "2026-11-04T00:00:00+00:00"}
        assert first.payload["new"]["value"] == 66
        assert first.payload["threshold"] == {"threshold": 65, "direction": "above"}
        assert first.payload["link"] == f"/products/{product}"
        saturation(session, product, 11, None)  # NULL keeps the state: 30 is still the last
        assert evaluate(session, ws, cutoff(11)) == {up: "no_source", down: "no_source"}
        saturation(session, product, 12, 70, version="001-sat")  # a new version: a reference
        saturation(session, product, 13, 72, version="001-sat")
        evaluate(session, ws, cutoff(12))
        evaluate(session, ws, cutoff(13))
        assert len(alerts(session, up)) == 2  # up was armed, but 70 isn't compared with 30
        saturation(session, product, 14, 30, version="001-sat")
        evaluate(session, ws, cutoff(13) + timedelta(hours=23))  # day 14 isn't over: not read
        assert len(alerts(session, down)) == 2
        evaluate(session, ws, cutoff(14))
        assert len(alerts(session, down)) == 3
        assert alerts(session, down)[-1].payload["new"]["model_version"] == "001-sat"


@pytest.mark.db
def test_a_watchlist_rule_evaluates_each_item_and_a_merged_one_as_its_survivor(
    db_engine: Engine,
) -> None:
    with Session(db_engine) as session:
        ws, lamp = setup(session)
        fan, merged, survivor = (Product(name=name) for name in ("Fan", "Old fan", "New fan"))
        session.add_all([fan, merged, survivor])
        session.flush()
        merged.merged_into_id = survivor.id
        pets = Watchlist(workspace_id=ws, name="Pets")
        session.add(pets)
        session.flush()
        session.add_all(
            WatchlistItem(workspace_id=ws, watchlist_id=pets.id, product_id=p)
            for p in (lamp, fan.id, merged.id)
        )
        other = rule(session, ws, "saturation_cross", ("product", merged.id), threshold=65,
                     direction="above")  # fmt: skip
        listed = rule(session, ws, "velocity_spike", ("watchlist", pets.id))
        for product in (lamp, fan.id, merged.id, survivor.id):
            velocity(session, product, 0, 20, 20)
        assert evaluate(session, ws, cutoff(0)) == {other: "no_source", listed: "ok"}
        stored = session.get_one(AlertRule, listed).last_value
        assert stored is not None
        watched = {f"product:{p}" for p in (lamp, fan.id, survivor.id)}
        assert stored["entities"].keys() == watched  # the merged id reads as its survivor
        for product in (lamp, survivor.id, merged.id):
            velocity(session, product, 1, 40, 20)
        velocity(session, fan.id, 1, 22, 20)
        saturation(session, survivor.id, 1, 50)
        evaluate(session, ws, cutoff(1))
        assert sorted(a.entity_id for a in alerts(session, listed)) == sorted(
            [str(lamp), str(survivor.id)]
        )
        assert session.get_one(AlertRule, other).last_value == {
            "status": "ok",
            "entities": {
                f"product:{survivor.id}": {
                    "value": 50.0,
                    "at": "2026-11-04T00:00:00+00:00",
                    "version": "000-sat",
                    "armed": True,
                }  # fmt: skip
            },
        }
