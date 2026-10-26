from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_core.models import (
    Category,
    Listing,
    MatchDecision,
    Product,
    ProductDailyFeature,
    Score,
    Source,
)
from pulso_core.scores import Explanation, ScoreRow, latest, version, write
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.scores import lifecycle, nightly, saturation, trend
from pulso_ml.scores.nightly import Prior, compute, hold, primary_families, run

DAY = date(2026, 12, 14)
WEEK_AGO, FIRST = DAY - timedelta(days=7), DAY - timedelta(days=30)
AT = cutoff(DAY)
FLAGS: dict[str, list[str]] = {"missed_runs": []}


def make(connection: Connection, n: int, category: int | None = None) -> list[UUID]:
    rows = [{"name": "Lamp", "category_id": category} for _ in range(n)]
    return list(connection.scalars(insert(Product).returning(Product.id), rows))


def feature(
    product: UUID,
    day: date,
    family: str = "cj_stock",
    v7: float | None = None,
    g7: float | None = None,
    gap: bool = False,
    **inputs: Any,
) -> dict[str, Any]:
    return {
        "product_id": product,
        "feature_date": day,
        "family": family,
        "feature_version": FEATURE_VERSION,
        "velocity_7d": v7,
        "growth_7d": g7,
        "coverage": Decimal(1),
        "has_gap": gap,
        "features": inputs or None,
        "gap_flags": FLAGS,
    }


def week(
    product: UUID, now: tuple[float, float], before: tuple[float, float]
) -> list[dict[str, Any]]:
    """A cj_stock series first seen 30 days before DAY, with its rows at DAY and a week before."""
    return [
        feature(product, FIRST),
        feature(product, WEEK_AGO, v7=before[0], g7=before[1]),
        feature(product, DAY, v7=now[0], g7=now[1]),
    ]


def market(connection: Connection) -> dict[str, UUID]:
    """Two days (DAY, DAY−7) and two demand families: a plateau (a), two risers (b, c), a NULL
    G7 (d), a search slope alone (e), and g with cj_stock since DAY−30 beside shp_inv since
    DAY−20. a, b and c have seller counts; nothing has a Trends capture."""
    a, b, c, d, e, g = make(connection, 6)
    rows = [*week(a, (20, 0.1), (15, 0.05)), *week(b, (30, 0.4), (20, 0.3))]
    rows += [*week(c, (40, 0.9), (20, 0.2)), *week(g, (30, 0.5), (20, 0.4))]
    rows += [feature(d, FIRST), feature(d, DAY)]
    rows += [feature(g, DAY - timedelta(days=20), "shp_inv"), feature(g, DAY, "shp_inv", 1, -1.0)]
    rows.append(feature(e, DAY, "gt_interest", gt_slope=0.3, gt_keywords=1, gt_as_of=None))
    rows += [
        feature(p, DAY, "shp_sellers", shp_sellers=s, shp_seller_g28=None, panel_size=0)
        for p, s in ((a, 1), (b, 4), (c, 9))
    ]
    connection.execute(insert(ProductDailyFeature), rows)
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "g": g}


def stored(session: Session, day: date = DAY) -> dict[tuple[str, UUID], Score]:
    rows = session.scalars(select(Score).where(Score.date == day))
    return {(s.kind, s.product_id): s for s in rows}


def explained(score: Score) -> Explanation:
    return Explanation.model_validate(score.explanation)


@pytest.mark.db
def test_a_night_appends_one_row_per_kind_and_product_and_a_rerun_adds_none(
    db_engine: Engine,
) -> None:
    with db_engine.begin() as connection:
        session, p = Session(connection), market(connection)
        assert run(session, DAY) == 13
        keys = connection.execute(
            select(Score.kind, Score.product_id, Score.date, Score.model_version)
        ).all()
        assert len(set(keys)) == len(keys) == 13
        expected = {("saturation", p[x]) for x in "abc"}
        expected |= {(kind, p[x]) for kind in ("trend", "lifecycle") for x in "abcdg"}
        assert {(kind, product) for kind, product, *_ in keys} == expected  # e: no family
        versions = {kind: v for kind, _, _, v in keys}
        assert versions == {
            "saturation": saturation.VERSION,
            "trend": trend.VERSION,
            "lifecycle": lifecycle.VERSION,
        }
        xmins = connection.scalars(text("SELECT xmin::text FROM scores ORDER BY id")).all()
        assert run(session, DAY) == 0
        assert connection.scalars(text("SELECT xmin::text FROM scores ORDER BY id")).all() == xmins


@pytest.mark.db
def test_a_trend_weight_change_appends_under_a_new_version_and_keeps_old_rows(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_engine.begin() as connection:
        session, _ = Session(connection), market(connection)
        run(session, DAY)
        before = connection.execute(text("SELECT id, xmin::text, value FROM scores")).all()
        monkeypatch.setattr(trend, "CONFIG", replace(trend.CONFIG, g7=0.5))
        new = version(trend.CONFIG)[0]
        assert new != trend.VERSION
        assert run(session, DAY) == 5
        appended = connection.execute(
            select(Score.kind, Score.model_version).where(Score.id > max(i for i, *_ in before))
        ).tuples()
        assert list(appended) == [("trend", new)] * 5
        old = connection.execute(text("SELECT id, xmin::text, value FROM scores")).all()
        assert set(before) <= set(old)


@pytest.mark.db
def test_no_value_is_a_null_row_with_its_reason_and_no_family_is_no_row(
    db_engine: Engine,
) -> None:
    with db_engine.begin() as connection:
        session, p = Session(connection), market(connection)
        older_trend(session, p["d"])  # d had a value the night before
        run(session, DAY)
        rows = stored(session)
        trend_d, stage_d = rows["trend", p["d"]], rows["lifecycle", p["d"]]
        assert trend_d.value is None and explained(trend_d).reason == "no velocity growth"
        assert explained(trend_d).model_version == trend.VERSION
        assert stage_d.stage is None and explained(stage_d).reason == "insufficient history"
        assert not [key for key in rows if key[1] == p["e"]]
        newest = {s.product_id: s for s in session.scalars(latest("trend"))}[p["d"]]
        assert (newest.date, newest.value) == (DAY, None)
        assert explained(newest).reason == "no velocity growth"


def older_trend(session: Session, product: UUID) -> None:
    """A valued trend row for the night before DAY, standing for an earlier run's."""
    explanation = nightly.unscored(trend.CONFIG, None)
    write(session, [ScoreRow(product, DAY - timedelta(days=1), "trend", 60, explanation)])


@pytest.mark.db
def test_one_primary_family_for_trend_and_lifecycle_and_present_inputs_have_an_as_of(
    db_engine: Engine,
) -> None:
    with db_engine.begin() as connection:
        session, p = Session(connection), market(connection)
        run(session, DAY)
        rows = stored(session)
        for kind in ("trend", "lifecycle"):  # cj_stock since DAY−30 beats shp_inv since DAY−20
            assert {c.family for c in explained(rows[kind, p["g"]]).components[:2]} == {"cj_stock"}
        assert rows["lifecycle", p["g"]].stage == "rising"  # shp_inv's −1.0 would decline
        for score in rows.values():
            for c in explained(score).components:
                assert (c.as_of is None) == c.missing, (score.kind, c.name)
                assert (c.freshness == 1.0) != c.missing, (score.kind, c.name)
            # Every scored row carries its confidence; a NULL row (no components) has none.
            explanation = explained(score)
            assert (explanation.confidence is None) == (not explanation.components), score.kind
        a = {c.name: c for c in explained(rows["lifecycle", p["a"]]).components}
        assert a["cj_stock_v7"].as_of == AT and a["cj_stock_v7_prev"].as_of == cutoff(WEEK_AGO)
        assert a["cj_stock_v7_prev"].freshness == 1.0  # a week old by design, as of its own row
        assert explained(rows["lifecycle", p["a"]]).confidence == pytest.approx(5 / 6)
        assert a["days_observed"].raw == 31 and a["cj_stock_acc"].raw == pytest.approx(0.05)
        assert explained(rows["lifecycle", p["a"]]).missing == ("age_days",)
        assert explained(rows["lifecycle", p["a"]]).coverage == pytest.approx(5 / 6)
        assert (rows["lifecycle", p["a"]].stage, explained(rows["lifecycle", p["a"]]).reason) == (
            "peaking",
            "plateau",
        )
        sellers = explained(rows["saturation", p["a"]]).components[0]
        assert (sellers.name, sellers.as_of) == ("shp_sellers", AT)
        penalty = explained(rows["trend", p["a"]]).penalties[0]
        assert penalty.raw == pytest.approx(float(rows["saturation", p["a"]].value or 0), abs=0.05)


@pytest.mark.db
def test_a_future_row_or_another_feature_version_never_changes_the_night(
    db_engine: Engine,
) -> None:
    with db_engine.begin() as connection:
        session, p = Session(connection), market(connection)
        expected = {(r.kind, r.product_id): r for r in compute(session, DAY)}
        (late,) = make(connection, 1)
        tomorrow = DAY + timedelta(days=1)
        rows = [feature(p["a"], tomorrow, v7=90, g7=2.0), feature(late, tomorrow, v7=9, g7=1)]
        rows.append(feature(p["b"], tomorrow, "shp_sellers", shp_sellers=50, panel_size=0))
        rows.append(feature(p["a"], WEEK_AGO, v7=1, g7=-2.0) | {"feature_version": "999-x"})
        connection.execute(insert(ProductDailyFeature), rows)
        assert {(r.kind, r.product_id): r for r in compute(session, DAY)} == expected


@pytest.mark.db
def test_lifecycle_keeps_its_stage_after_one_disagreeing_night_and_switches_after_two(
    db_engine: Engine,
) -> None:
    with db_engine.begin() as connection:
        session, (x,) = Session(connection), make(connection, 1)
        tonight = ["rising", "peaking", "rising", "peaking", "peaking"]  # each night's rule
        rows = [feature(x, FIRST)]
        for i, stage in enumerate(tonight):
            night = DAY + timedelta(days=i)
            g7 = 0.5 if stage == "rising" else 0.1  # a plateau under +20%
            rows += [
                feature(x, night - timedelta(days=7), v7=20, g7=0.4),
                feature(x, night, v7=30, g7=g7),
            ]
        connection.execute(insert(ProductDailyFeature), rows)
        shown = []
        for i in range(len(tonight)):
            run(session, DAY + timedelta(days=i))
            score = stored(session, DAY + timedelta(days=i))["lifecycle", x]
            shown.append((score.stage, explained(score).pending, explained(score).reason))
        assert shown == [
            ("rising", None, "growing"),
            ("rising", "peaking", "plateau"),
            ("rising", None, "growing"),
            ("rising", "peaking", "plateau"),
            ("peaking", None, "plateau"),
        ]


@pytest.mark.db
def test_a_gap_night_or_a_family_change_holds_nothing(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        session, (y, z) = Session(connection), make(connection, 2)
        night2, night3 = DAY + timedelta(days=1), DAY + timedelta(days=2)
        rows = [*week(y, (30, 0.5), (20, 0.4)), *week(z, (30, 0.5), (20, 0.4))]
        rows += [feature(y, night2 - timedelta(days=7), v7=20, g7=0.4)]
        rows += [feature(y, night2, v7=30, g7=0.5, gap=True)]  # values kept, flagged: no stage
        rows += [
            feature(y, night3 - timedelta(days=7), v7=20, g7=0.4),
            feature(y, night3, v7=30, g7=0.1),
        ]
        rows += [feature(z, DAY - timedelta(days=20), "shp_inv")]  # z's cj_stock stops on night 2
        rows += [feature(z, night2 - timedelta(days=7), "shp_inv", 20, 0.4)]
        rows += [feature(z, night2, "shp_inv", 30, 0.1)]
        connection.execute(insert(ProductDailyFeature), rows)
        for day in (DAY, night2, night3):
            run(session, day)
        assert [stored(session, d)["lifecycle", y].stage for d in (DAY, night2, night3)] == [
            "rising",
            None,
            "peaking",
        ]
        z2 = stored(session, night2)["lifecycle", z]
        assert (z2.stage, explained(z2).pending) == ("peaking", None)
        assert explained(z2).components[4].raw == 22  # shp_inv's own days, never cj_stock's


@pytest.mark.db
def test_lifecycle_reads_launch_dates_and_delistings_as_of_the_cutoff(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        session, (k, m, n) = Session(connection), make(connection, 3)
        rows = [*week(k, (30, 0.5), (20, 0.4)), *week(m, (30, 0.5), (20, 0.4))]
        rows += week(n, (30, 0.5), (20, 0.4))
        connection.execute(insert(ProductDailyFeature), rows)
        cj = connection.scalar(select(Source.id).where(Source.key == "cj"))
        at = datetime.combine(DAY, datetime.min.time(), UTC)
        for product, listing in (
            (k, {"source_created_at": at - timedelta(days=10)}),  # launched 10 days ago
            (k, {"source_published_at": at - timedelta(days=5)}),  # its later listing
            (m, {"delisted_at": at - timedelta(days=2)}),  # delisted before the cutoff
            (n, {"delisted_at": AT, "source_created_at": AT}),  # both after it
        ):
            listing_id = connection.scalar(
                insert(Listing)
                .values(source_id=cj, external_id=uuid4().hex, url="u", title="t", **listing)
                .returning(Listing.id)
            )
            connection.execute(
                insert(MatchDecision).values(
                    actor="test",
                    action="link",
                    listing_id=listing_id,
                    to_product_id=product,
                    decided_at=at - timedelta(days=20),
                )
            )
        run(session, DAY)
        found = stored(session)
        stages = {
            x: (found["lifecycle", x].stage, explained(found["lifecycle", x]).reason)
            for x in (k, m, n)
        }
        assert stages == {
            k: ("emerging", "new and growing"),
            m: ("dead", "delisted"),
            n: ("rising", "growing"),  # delisted at the cutoff, launched after it: neither counts
        }
        age = explained(found["lifecycle", k]).components[5]
        assert (age.raw, age.source, age.missing) == (10, "cj", False)


@pytest.mark.db
def test_categories_are_read_with_their_ancestors(
    db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with db_engine.begin() as connection:
        session = Session(connection)
        connection.execute(
            insert(Category),
            [
                {"id": 1, "parent_id": None, "name": "Home", "path": "Home"},
                {"id": 2, "parent_id": 1, "name": "Lamps", "path": "Home > Lamps"},
                {"id": 3, "parent_id": 1, "name": "Rugs", "path": "Home > Rugs"},
            ],
        )
        a, b = make(connection, 2, category=2)
        (c,) = make(connection, 1, category=3)
        rows = [*week(a, (20, 0.1), (15, 0.05)), *week(b, (30, 0.4), (20, 0.3))]
        connection.execute(insert(ProductDailyFeature), rows + week(c, (40, 0.9), (20, 0.2)))
        monkeypatch.setattr(trend, "CONFIG", replace(trend.CONFIG, min_n=3))
        run(session, DAY)
        growth = explained(stored(session)["trend", a]).components[0]
        assert growth.normalization is not None and growth.normalization.category_id == 1


def test_a_stage_shows_once_its_rule_matched_two_nights_in_a_row() -> None:
    rising = Prior("rising", None, "cj_stock")
    assert hold("rising", None, "cj_stock") == ("rising", None)  # nothing stored yet
    assert hold("peaking", rising, "cj_stock") == ("rising", "peaking")
    assert hold("peaking", rising._replace(pending="peaking"), "cj_stock") == ("peaking", None)
    assert hold("declining", rising._replace(pending="peaking"), "cj_stock") == (
        "rising",
        "declining",
    )
    assert hold("rising", rising._replace(pending="peaking"), "cj_stock") == ("rising", None)
    assert hold(None, rising, "cj_stock") == (None, None)  # no stage is never held over
    assert hold(None, rising._replace(pending="peaking"), "cj_stock") == (None, None)
    assert hold("peaking", Prior(None, None, "cj_stock"), "cj_stock") == ("peaking", None)
    assert hold("peaking", rising, "shp_inv") == ("peaking", None)  # a new family restarts


def test_the_primary_family_is_the_one_observed_longest_then_by_name() -> None:
    p, q = UUID(int=1), UUID(int=2)
    first = {
        (p, "shp_inv"): DAY - timedelta(days=40),
        (p, "cj_stock"): DAY - timedelta(days=30),
        (q, "shp_inv"): DAY - timedelta(days=30),
        (q, "cj_stock"): DAY - timedelta(days=30),
    }
    assert primary_families(first.keys(), first) == {p: "shp_inv", q: "cj_stock"}


def test_the_cli_refuses_a_day_still_being_collected() -> None:
    with pytest.raises(SystemExit):
        nightly.main([datetime.now(UTC).date().isoformat()])
