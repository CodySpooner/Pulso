from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Connection, func, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from pulso_core.models import Product, Score
from pulso_core.scores import (
    CADENCE,
    Component,
    Explanation,
    Penalty,
    ScoreRow,
    confidence,
    explain,
    fresh,
    latest,
    version,
    write,
)

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")
AS_OF = datetime(2026, 12, 14, 6, 10, tzinfo=UTC)
CUTOFF = datetime(2026, 12, 15, tzinfo=UTC)  # the scored day's end (DEC-031)


@dataclass(frozen=True)
class TrendConfig:
    revision: int = 1
    weights: dict[str, float] = field(
        default_factory=lambda: {"cj_stock_g7": 0.4, "gt_slope": 0.2, "ads_growth": 0.4}
    )


CONFIG = TrendConfig()
FIXTURE = {  # name: (family, source, z)
    "cj_stock_g7": ("cj_stock", "cj", 1.5),
    "gt_slope": ("trends", "google_trends", -1.0),
    "ads_growth": ("ads", "meta_ads", 0.5),
}


def inputs(*missing: str) -> list[Component]:
    """The fixture's inputs; a missing one has no source yet."""
    components = []
    for name, weight in CONFIG.weights.items():
        family, source, z = FIXTURE[name]
        if name in missing:
            components.append(
                Component(name=name, family=family, source=None, weight=weight, missing=True)
            )
        else:
            components.append(
                Component(
                    name=name, family=family, source=source, weight=weight, raw=z, z=z, as_of=AS_OF
                )
            )
    return components


def test_a_weights_change_makes_a_new_model_version() -> None:
    model_version, digest = version(TrendConfig())
    assert version(TrendConfig()) == (model_version, digest)
    assert model_version == f"001-{digest[:12]}" and len(digest) == 64
    changed = TrendConfig(weights={"cj_stock_g7": 0.5, "gt_slope": 0.2, "ads_growth": 0.3})
    assert version(changed)[0].startswith("001-") and version(changed)[0] != model_version
    assert version(TrendConfig(revision=2))[0].startswith("002-")


def test_every_input_present_keeps_the_configured_weights() -> None:
    value, explanation = explain(TrendConfig(), inputs(), as_of=CUTOFF)
    assert value == pytest.approx(0.4 * 1.5 - 0.2 + 0.4 * 0.5)
    assert [c.weight_eff for c in explanation.components] == pytest.approx([0.4, 0.2, 0.4])
    assert sum(c.contribution or 0 for c in explanation.components) == pytest.approx(value)
    assert explanation.missing == () and explanation.coverage == 1
    assert explanation.model_version == version(TrendConfig())[0]


def test_a_missing_input_gets_weight_zero_and_the_rest_renormalise() -> None:
    value, explanation = explain(TrendConfig(), inputs("ads_growth"), as_of=CUTOFF)
    assert [c.weight_eff for c in explanation.components] == pytest.approx([2 / 3, 1 / 3, 0])
    assert value == pytest.approx(2 / 3 * 1.5 - 1 / 3)
    ads = explanation.components[2]
    assert ads.contribution is None and ads.z is None and ads.source is None
    assert explanation.missing == ("ads_growth",)
    assert explanation.coverage == pytest.approx(0.6)


def test_every_input_missing_is_a_null_value_never_zero() -> None:
    value, explanation = explain(
        TrendConfig(), inputs("cj_stock_g7", "gt_slope", "ads_growth"), as_of=CUTOFF
    )
    assert value is None
    assert explanation.missing == ("cj_stock_g7", "gt_slope", "ads_growth")
    assert explanation.coverage == 0
    assert all(c.weight_eff == 0 and c.contribution is None for c in explanation.components)


def test_an_explanation_round_trips_and_keeps_missing_honest() -> None:
    _, explanation = explain(TrendConfig(), inputs("ads_growth"), as_of=CUTOFF)
    assert Explanation.model_validate(explanation.model_dump(mode="json")) == explanation
    with pytest.raises(ValidationError, match="missing"):
        Explanation.model_validate(explanation.model_dump() | {"missing": ()})
    with pytest.raises(ValidationError, match="prompt_version"):
        Component(name="refunds", family="reviews", source="ai", weight=1, ai_derived=True)


def test_a_missing_penalty_is_named_in_missing_after_the_components() -> None:
    _, explanation = explain(TrendConfig(), inputs("ads_growth"), as_of=CUTOFF)
    saturation = Penalty(name="saturation", source="shopify_stores", missing=True)
    fields = explanation.model_dump() | {"penalties": [saturation.model_dump()]}
    with pytest.raises(ValidationError, match="missing"):
        Explanation.model_validate(fields)
    named = Explanation.model_validate(fields | {"missing": ("ads_growth", "saturation")})
    assert Explanation.model_validate(named.model_dump(mode="json")) == named
    present = saturation.model_copy(update={"missing": False, "raw": 73.3, "points": 6.99})
    Explanation.model_validate(fields | {"penalties": [present.model_dump()]})


@pytest.mark.parametrize(
    ("source", "cadence"), [("cj", timedelta(days=1)), ("google_trends", timedelta(weeks=1))]
)
def test_freshness_is_1_to_1_5_cadences_then_0_5_to_3_then_stale(
    source: str, cadence: timedelta
) -> None:
    assert CADENCE[source] == cadence

    def aged(age: timedelta) -> Component:
        captured = CUTOFF - age
        c = Component(name="x", family="f", source=source, weight=1, z=1, as_of=captured)
        return fresh(c, CUTOFF)

    tick = timedelta(microseconds=1)
    assert aged(timedelta(0)).freshness == aged(1.5 * cadence).freshness == 1.0
    assert aged(1.5 * cadence + tick).freshness == aged(3 * cadence).freshness == 0.5
    assert not aged(3 * cadence).missing
    stale = aged(3 * cadence + tick)
    assert (stale.missing, stale.stale, stale.freshness) == (True, True, None)
    assert stale.as_of == CUTOFF - 3 * cadence - tick  # kept: the UI's "last seen"


def test_confidence_weighs_each_present_input_by_its_freshness() -> None:
    components = inputs("ads_growth")  # the lamp, ads missing; the slope 12 days old: halved
    components[1] = components[1].model_copy(update={"as_of": CUTOFF - timedelta(days=12)})
    value, explanation = explain(TrendConfig(), components, as_of=CUTOFF)
    assert value == pytest.approx(2 / 3 * 1.5 - 1 / 3)  # freshness never moves the value
    assert [c.freshness for c in explanation.components] == [1.0, 0.5, None]
    assert explanation.coverage == pytest.approx(0.6)
    assert explanation.confidence == pytest.approx((0.4 * 1.0 + 0.2 * 0.5) / 1.0)
    assert explanation.cautions == ("stale_input",)
    fresh_only = explain(TrendConfig(), inputs("ads_growth"), as_of=CUTOFF)[1]
    assert fresh_only.confidence == pytest.approx(0.6) and fresh_only.cautions == ()


def test_an_input_older_than_3_cadences_is_missing_and_the_rest_renormalise() -> None:
    components = inputs("ads_growth")
    components[1] = components[1].model_copy(update={"as_of": CUTOFF - timedelta(days=22)})
    value, explanation = explain(TrendConfig(), components, as_of=CUTOFF)
    slope = explanation.components[1]
    assert (slope.missing, slope.stale, slope.weight_eff, slope.contribution) == (
        True,
        True,
        0.0,
        None,
    )
    assert explanation.missing == ("gt_slope", "ads_growth")
    assert value == pytest.approx(1.5)  # cj_stock_g7 alone
    assert explanation.coverage == explanation.confidence == pytest.approx(0.4)
    assert explanation.cautions == ("stale_input",)
    assert Explanation.model_validate(explanation.model_dump(mode="json")) == explanation


def test_an_input_without_a_capture_time_or_a_cadence_has_no_freshness_and_says_why() -> None:
    no_time, slope, ads = inputs()
    components = [
        no_time.model_copy(update={"as_of": None}),
        slope,
        ads.model_copy(update={"source": "meta_ads"}),
    ]
    _, explanation = explain(TrendConfig(), components, as_of=CUTOFF)
    found = [(c.freshness, c.freshness_reason) for c in explanation.components]
    assert found == [(None, "no capture time"), (1.0, None), (None, "no cadence for meta_ads")]
    assert explanation.confidence == 1.0  # never stale without either (DEC-238's rule)
    assert explanation.cautions == ()


def test_unweighted_inputs_count_one_each() -> None:
    parts = [
        Component(name=name, family="cj_stock", source="cj", weight=0, raw=1, as_of=AS_OF)
        for name in ("cj_stock_v7", "cj_stock_g7")
    ]
    parts.append(Component(name="age_days", family="launch", source=None, weight=0, missing=True))
    assert confidence([fresh(p, CUTOFF) for p in parts]) == pytest.approx(2 / 3)


def test_rows_stored_before_freshness_still_validate() -> None:
    _, explanation = explain(TrendConfig(), inputs("ads_growth"), as_of=CUTOFF)
    old = explanation.model_dump(mode="json")
    for key in ("confidence", "cautions"):
        del old[key]
    for component in old["components"]:
        for key in ("freshness", "stale", "freshness_reason"):
            del component[key]
    found = Explanation.model_validate(old)
    assert found.confidence is None
    assert all(c.freshness is None and not c.stale for c in found.components)
    opportunity = old | {"confidence": 0.7, "cautions": ["duty_not_set"]}  # p4-20's meaning
    assert Explanation.model_validate(opportunity).cautions == ("duty_not_set",)
    with pytest.raises(ValidationError, match="stale"):
        Component(name="gt_slope", family="trends", source="google_trends", weight=1, stale=True)


def make_product(connection: Connection) -> UUID:
    return connection.execute(
        insert(Product).values(name="Lamp").returning(Product.id)
    ).scalar_one()


def night(product: UUID, day: date, config: TrendConfig = CONFIG) -> ScoreRow:
    value, explanation = explain(config, inputs("ads_growth"), as_of=CUTOFF)
    return ScoreRow(product, day, "trend", None if value is None else 50 + value, explanation)


@pytest.mark.db
@pytest.mark.parametrize(
    "mutation", ["UPDATE scores SET value = 1", "DELETE FROM scores", "TRUNCATE scores"]
)
def test_scores_are_append_only(db_engine: Engine, mutation: str) -> None:
    with db_engine.begin() as connection:
        write(Session(connection), [night(make_product(connection), date(2026, 12, 14))])
        with pytest.raises(DBAPIError, match="scores is append-only"), connection.begin_nested():
            connection.execute(text(mutation))
        assert connection.scalar(select(func.count()).select_from(Score)) == 1


@pytest.mark.db
def test_writing_the_same_night_twice_inserts_nothing_new(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        session, product = Session(connection), make_product(connection)
        rows = [night(product, date(2026, 12, 14)), night(product, date(2026, 12, 13))]
        assert write(session, rows) == 2
        xmins = connection.scalars(text("SELECT xmin::text FROM scores ORDER BY date")).all()
        assert write(session, rows) == 0
        assert connection.scalars(text("SELECT xmin::text FROM scores ORDER BY date")).all() == (
            xmins
        )
        changed = TrendConfig(weights={"cj_stock_g7": 0.5, "gt_slope": 0.2, "ads_growth": 0.3})
        assert write(session, [night(product, date(2026, 12, 14), changed)]) == 1
        assert write(session, []) == 0


@pytest.mark.db
def test_latest_reads_each_products_newest_row_of_a_kind(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        session = Session(connection)
        a, b = make_product(connection), make_product(connection)
        old, new = date(2026, 12, 13), date(2026, 12, 14)
        _, empty = explain(
            TrendConfig(), inputs("cj_stock_g7", "gt_slope", "ads_growth"), as_of=CUTOFF
        )
        write(session, [night(a, old), night(a, new), night(b, old)])
        write(session, [ScoreRow(b, new, "saturation", None, empty)])
        rows = {s.product_id: s for s in session.scalars(latest("trend"))}
        assert {p: s.date for p, s in rows.items()} == {a: new, b: old}
        assert Explanation.model_validate(rows[a].explanation).missing == ("ads_growth",)
        assert [s.value for s in session.scalars(latest("saturation"))] == [None]
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        sql = str(latest("trend").compile(connection, compile_kwargs={"literal_binds": True}))
        plan = "\n".join(connection.exec_driver_sql("EXPLAIN " + sql).scalars())
        assert "Index Scan Backward using uq_scores_kind_product_id_date_model_version" in plan


@pytest.mark.db
@pytest.mark.parametrize(
    "overrides",
    [
        {"value": 100.1},
        {"kind": "opportunity"},
        {"stage": "rising"},
        {"kind": "lifecycle"},
        {"kind": "lifecycle", "value": None, "stage": "hot"},
    ],
    ids=["value-range", "kind", "stage-on-trend", "value-on-lifecycle", "stage-values"],
)
def test_score_rows_hold_only_known_values(db_engine: Engine, overrides: dict[str, object]) -> None:
    with db_engine.begin() as connection, pytest.raises(IntegrityError):
        row = {"product_id": make_product(connection), "date": date(2026, 12, 14)}
        row |= {"kind": "trend", "model_version": "001-x", "value": 50, "explanation": {}}
        connection.execute(insert(Score).values(row | overrides))


@pytest.mark.db
def test_phase4_round_trip_refuses_to_drop_scores(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    version_num = text("SELECT version_num FROM alembic_version")
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0015")
        assert connection.scalar(text("SELECT to_regclass('scores')")) is None
        command.upgrade(config, "head")
        assert connection.scalar(version_num) == "0024"
        lifecycle = ScoreRow(
            make_product(connection),
            date(2026, 12, 14),
            "lifecycle",
            None,
            explain(TrendConfig(), inputs(), as_of=CUTOFF)[1],
            "rising",
        )
        write(Session(connection), [lifecycle])
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0015")
        assert connection.scalar(version_num) == "0024"
