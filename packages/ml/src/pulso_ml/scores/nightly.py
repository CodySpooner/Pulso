"""SC-6: one UTC day's scores from its stored feature rows (SPEC §7, DEC-326).

`run(session, d)` reads product_daily_features at d and d−7 (each row holds only captures
before its day's cutoff, DEC-031) and the night before's lifecycle rows, then appends
Saturation, Trend and Lifecycle rows through pulso_core.scores.write: never an UPDATE or a
DELETE, and nothing for a day without feature rows. `python -m pulso_ml.scores.nightly <day>`
runs one day once.
"""

import argparse
from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, NamedTuple, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.models import Category, Listing, Product, ProductDailyFeature, Score, Source
from pulso_core.scores import Component, Explanation, Kind, ScoreRow, Stage, version, write
from pulso_ml.features.daily import cutoff
from pulso_ml.features.demand import FEATURE_VERSION
from pulso_ml.features.repository import FAMILIES, AsOf
from pulso_ml.scores import lifecycle, saturation, trend
from pulso_ml.scores.velocity import family_velocity

Rows = Mapping[tuple[UUID, str], ProductDailyFeature]


class Prior(NamedTuple):
    """The night before's lifecycle row: the stage it shows, its pending stage, its family."""

    stage: Stage | None
    pending: Stage | None
    family: str


class Launch(NamedTuple):
    at: datetime
    source: str


def hold(
    stage: Stage | None, prior: Prior | None, family: str
) -> tuple[Stage | None, Stage | None]:
    """(stage stored, pending stage): a new stage shows once its rule matched two nights in a row
    (vault Lifecycle Stage). No stage tonight, or none the night before in this family, holds
    nothing: a gap is never bridged and families are never spliced (Demand Signals rule 2)."""
    if stage is None or prior is None or prior.family != family or prior.stage in (None, stage):
        return stage, None
    if prior.pending == stage:
        return stage, None
    return prior.stage, stage


def stamped(explanation: Explanation, at: datetime) -> Explanation:
    """A present input whose feature row carries no capture time is as of the cutoff (imp-427)."""
    components = tuple(
        c if c.missing or c.as_of else c.model_copy(update={"as_of": at})
        for c in explanation.components
    )
    return explanation.model_copy(update={"components": components})


def unscored(config: Any, reason: str | None) -> Explanation:
    """A NULL value's explanation: its version and why, so `latest()` never serves an older
    value as tonight's (DEC-326 b)."""
    model_version, digest = version(config)
    return Explanation(
        model_version=model_version,
        config_digest=digest,
        components=(),
        missing=(),
        coverage=0.0,
        reason=reason,
    )


def primary_families(
    rows: Collection[tuple[UUID, str]], first: Mapping[Any, date]
) -> dict[UUID, str]:
    """Demand Signals rules 1–3 until the owner's R-12 memo names a family: of a product's demand
    families with a row on the day, the one with the earliest first row; a tie goes by name."""
    primary: dict[UUID, str] = {}
    for product, family in sorted(rows, key=lambda key: (first[key], key[1])):
        primary.setdefault(product, family)
    return primary


class Night:
    """One day's stored feature rows, read once for every score."""

    def __init__(self, session: Session, day: date) -> None:
        self.session, self.day, self.at = session, day, cutoff(day)
        feature = ProductDailyFeature
        current = feature.feature_version == FEATURE_VERSION
        week_ago = day - timedelta(days=7)
        rows = self.session.scalars(
            select(feature).where(current, feature.feature_date.in_((self.day, week_ago)))
        ).all()
        self.now = [r for r in rows if r.feature_date == self.day]
        self.before: Rows = {
            (r.product_id, r.family): r for r in rows if r.feature_date == week_ago
        }
        self.first = dict(
            ((p, fam), d)
            for p, fam, d in self.session.execute(
                select(feature.product_id, feature.family, func.min(feature.feature_date))
                .where(
                    current, feature.family.in_(list(FAMILIES)), feature.feature_date <= self.day
                )
                .group_by(feature.product_id, feature.family)
            ).tuples()
        )
        self.demand: Rows = {(r.product_id, r.family): r for r in self.now if r.family in FAMILIES}
        self.primary = primary_families(self.demand.keys(), self.first)

    def lineages(self, products: Collection[UUID]) -> dict[UUID, list[int]]:
        """Each product's category and its ancestors, nearest first.

        ponytail: products.category_id is today's mapping; it has no history to read as of d."""
        parent = dict(self.session.execute(select(Category.id, Category.parent_id)).tuples().all())
        category = dict(
            self.session.execute(
                select(Product.id, Product.category_id).where(Product.id.in_(products))
            )
            .tuples()
            .all()
        )
        lineages: dict[UUID, list[int]] = {}
        for product in products:
            chain: list[int] = []
            at = category.get(product)
            while at is not None:
                chain.append(at)
                at = parent.get(at)
            lineages[product] = chain
        return lineages

    def row(self, product: UUID, kind: Kind, scored: Any, config: Any) -> ScoreRow:
        explanation = scored.explanation
        stored = stamped(explanation, self.at) if explanation else unscored(config, scored.reason)
        return ScoreRow(product, self.day, kind, scored.value, stored)

    def scores(self) -> list[ScoreRow]:
        sellers = [r for r in self.now if r.family == "shp_sellers"]
        lineage = self.lineages({r.product_id for r in sellers} | self.primary.keys())
        saturations = saturation.saturation_scores(
            sellers, {r.product_id: lineage[r.product_id] for r in sellers}
        )
        trends = trend.trend_scores(
            self.now,
            self.before.values(),
            {p: lineage[p] for p in self.primary},
            self.primary,
            {p: s.value for p, s in saturations.items()},
        )
        rows = [self.row(p, "saturation", s, saturation.CONFIG) for p, s in saturations.items()]
        rows += [self.row(p, "trend", t, trend.CONFIG) for p, t in trends.items()]
        return rows + self.stages()

    def listings(self) -> tuple[dict[UUID, Launch], set[UUID]]:
        """Each product's earliest source launch date, and the products whose every listing was
        delisted by the cutoff, over its listings as of then (R-15)."""
        members = {
            listing: p
            for listing, p in AsOf(self.session, self.at).membership().items()
            if p in self.primary
        }
        launched: dict[UUID, Launch] = {}
        live: dict[UUID, bool] = {}  # a listing still live at the cutoff
        for listing, source, created, published, delisted in self.session.execute(
            select(
                Listing.id,
                Source.key,
                Listing.source_created_at,
                Listing.source_published_at,
                Listing.delisted_at,  # today's value, judged against the cutoff as market.live()
            )
            .join(Source, Source.id == Listing.source_id)
            .where(Listing.id.in_(members))
        ):
            product = members[listing]
            live[product] = live.get(product, False) or delisted is None or delisted >= self.at
            at = created or published  # today's values too: a re-crawl rewrites them
            if at is None or at >= self.at:
                continue
            if product not in launched or at < launched[product].at:
                launched[product] = Launch(at, source)
        return launched, {product for product, alive in live.items() if not alive}

    def priors(self, model_version: str) -> dict[UUID, Prior]:
        found: dict[UUID, Prior] = {}
        for score in self.session.scalars(
            select(Score).where(
                Score.kind == "lifecycle",
                Score.date == self.day - timedelta(days=1),
                Score.model_version == model_version,
            )
        ):
            explanation = Explanation.model_validate(score.explanation)
            stage = cast(Stage | None, score.stage)  # the stage_values CHECK holds it to Stage
            found[score.product_id] = Prior(
                stage, explanation.pending, explanation.components[0].family
            )
        return found

    def stages(self) -> list[ScoreRow]:
        model_version, digest = version(lifecycle.CONFIG)
        priors = self.priors(model_version)
        launched, delisted = self.listings()
        rows: list[ScoreRow] = []
        for product, family in self.primary.items():
            now, prev = self.demand[product, family], self.before.get((product, family))
            days = (self.day - self.first[product, family]).days + 1  # Velocity's and Lifecycle's
            velocity = family_velocity(now, prev, days)
            launch = launched.get(product)
            age = None if launch is None else (self.day - launch.at.astimezone(UTC).date()).days
            stage = lifecycle.lifecycle_stage(
                v7=now.velocity_7d,
                v7_prev=prev.velocity_7d if prev else None,
                g7=now.growth_7d,
                g7_prev=prev.growth_7d if prev else None,
                days_observed=days,
                has_gap=now.has_gap or (prev is not None and prev.has_gap),
                age_days=age,
                delisted_all=product in delisted,
            )
            shown, pending = hold(stage.name, priors.get(product), family)
            components = self.inputs(family, now, prev, velocity.acc.value, days, launch, age)
            missing = tuple(c.name for c in components if c.missing)
            explanation = Explanation(
                model_version=model_version,
                config_digest=digest,
                components=components,
                missing=missing,
                coverage=1 - len(missing) / len(components),  # unweighted: the share present
                reason=stage.reason,
                pending=pending,
            )
            rows.append(ScoreRow(product, self.day, "lifecycle", None, explanation, shown))
        return rows

    def inputs(
        self,
        family: str,
        now: ProductDailyFeature,
        prev: ProductDailyFeature | None,
        acc: float | None,
        days: int,
        launch: Launch | None,
        age: int | None,
    ) -> tuple[Component, ...]:
        """Lifecycle's rule inputs as unweighted components: rules read them, no sum does."""
        source, then = FAMILIES[family].source, cutoff(self.day - timedelta(days=7))
        prev_gap = prev is not None and prev.has_gap

        def part(name: str, raw: float | None, at: datetime, gap: bool, **more: Any) -> Component:
            more = {"family": family, "source": source} | more
            missing = raw is None
            return Component(
                name=name,
                weight=0,
                raw=raw,
                as_of=None if missing else at,
                missing=missing,
                gap=gap,
                **more,
            )

        return (
            part(f"{family}_v7", now.velocity_7d, self.at, now.has_gap),
            part(f"{family}_v7_prev", prev.velocity_7d if prev else None, then, prev_gap),
            part(f"{family}_g7", now.growth_7d, self.at, now.has_gap),
            part(f"{family}_acc", acc, self.at, now.has_gap or prev_gap),
            part("days_observed", days, self.at, False),
            part(
                "age_days",
                age,
                self.at,
                False,
                family="launch",
                source=launch.source if launch else None,
            ),
        )


def compute(session: Session, day: date) -> list[ScoreRow]:
    """Day d's Saturation, Trend and Lifecycle rows from its stored feature rows (DEC-326).

    - Saturation: every product with a `shp_sellers` row on d.
    - Trend and Lifecycle: every product with a demand-family row on d, read in its primary
      family alone: the family with the earliest first row, a tie by name (Demand Signals
      rules 1–3). A product with none gets no row: no source.
    - No value is a NULL row whose explanation names the reason, never 0 and never no row.
    - Lifecycle stores a new stage once its rule matched two nights in a row; until then the
      night before's stage, with tonight's in `pending`. Its explanation's `reason` is
      tonight's rule; its inputs are unweighted components.
    - `days_observed` is the days since the family's first row, d included, for both Velocity
      and Lifecycle. A present input with no capture time on its row is as of the cutoff.
    Only rows dated d and d−7 (and first-row dates up to d) are read: nothing is interpolated.
    """
    return Night(session, day).scores()


def run(session: Session, day: date) -> int:
    """Computes and appends day's rows, returning how many were new; the caller commits."""
    return write(session, compute(session, day))


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Scores one UTC day from its feature rows.")
    parser.add_argument("day", type=date.fromisoformat, help="YYYY-MM-DD, before today (UTC)")
    day = parser.parse_args(argv).day
    if day >= datetime.now(UTC).date():
        parser.error(f"{day} is not over yet (UTC)")
    from pulso_core.db import get_session

    with get_session() as session:
        written = run(session, day)
        session.commit()
    print(f"scores_done day={day} written={written}")


if __name__ == "__main__":
    main()
