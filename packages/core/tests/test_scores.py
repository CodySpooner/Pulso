from dataclasses import dataclass, field
from datetime import UTC, date, datetime
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
from pulso_core.scores import Component, Explanation, ScoreRow, explain, latest, version, write

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")
AS_OF = datetime(2026, 12, 14, 6, 10, tzinfo=UTC)


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
    value, explanation = explain(TrendConfig(), inputs())
    assert value == pytest.approx(0.4 * 1.5 - 0.2 + 0.4 * 0.5)
    assert [c.weight_eff for c in explanation.components] == pytest.approx([0.4, 0.2, 0.4])
    assert sum(c.contribution or 0 for c in explanation.components) == pytest.approx(value)
    assert explanation.missing == () and explanation.coverage == 1
    assert explanation.model_version == version(TrendConfig())[0]


def test_a_missing_input_gets_weight_zero_and_the_rest_renormalise() -> None:
    value, explanation = explain(TrendConfig(), inputs("ads_growth"))
    assert [c.weight_eff for c in explanation.components] == pytest.approx([2 / 3, 1 / 3, 0])
    assert value == pytest.approx(2 / 3 * 1.5 - 1 / 3)
    ads = explanation.components[2]
    assert ads.contribution is None and ads.z is None and ads.source is None
    assert explanation.missing == ("ads_growth",)
    assert explanation.coverage == pytest.approx(0.6)


def test_every_input_missing_is_a_null_value_never_zero() -> None:
    value, explanation = explain(TrendConfig(), inputs("cj_stock_g7", "gt_slope", "ads_growth"))
    assert value is None
    assert explanation.missing == ("cj_stock_g7", "gt_slope", "ads_growth")
    assert explanation.coverage == 0
    assert all(c.weight_eff == 0 and c.contribution is None for c in explanation.components)


def test_an_explanation_round_trips_and_keeps_missing_honest() -> None:
    _, explanation = explain(TrendConfig(), inputs("ads_growth"))
    assert Explanation.model_validate(explanation.model_dump(mode="json")) == explanation
    with pytest.raises(ValidationError, match="missing"):
        Explanation.model_validate(explanation.model_dump() | {"missing": ()})
    with pytest.raises(ValidationError, match="prompt_version"):
        Component(name="refunds", family="reviews", source="ai", weight=1, ai_derived=True)


def make_product(connection: Connection) -> UUID:
    return connection.execute(
        insert(Product).values(name="Lamp").returning(Product.id)
    ).scalar_one()


def night(product: UUID, day: date, config: TrendConfig = CONFIG) -> ScoreRow:
    value, explanation = explain(config, inputs("ads_growth"))
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
        _, empty = explain(TrendConfig(), inputs("cj_stock_g7", "gt_slope", "ads_growth"))
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
        assert connection.scalar(version_num) == "0020"
        lifecycle = ScoreRow(
            make_product(connection),
            date(2026, 12, 14),
            "lifecycle",
            None,
            explain(TrendConfig(), inputs())[1],
            "rising",
        )
        write(Session(connection), [lifecycle])
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0015")
        assert connection.scalar(version_num) == "0020"
