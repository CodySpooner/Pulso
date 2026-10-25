"""The contract every Phase 4 score writes and reads (SPEC §7, DEC-040, DEC-047, DEC-306).

Score maths lives with each score (SC-2..SC-5). This module holds the explanation shape, the
version rule, the DEC-040 renormalisation, the append-only writer and the latest-row read.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date as date_type
from typing import TYPE_CHECKING, Literal, NamedTuple, Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import Score

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

Kind = Literal["trend", "saturation", "lifecycle", "risk", "refund_risk"]  # scores' CHECK
Stage = Literal["emerging", "rising", "peaking", "declining", "dead"]


class Normalization(BaseModel):
    """The products a robust z was taken over (vault Score Definitions §4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_id: int | None  # the category used, after any fallback; None: every product
    n: int = Field(ge=1)  # products with a value there


class Component(BaseModel):
    """One input as the explanation records it.

    Missing with no `source` reads "no source yet"; missing with a source reads "insufficient
    signal" (vault Score Definitions §7). A missing input has weight_eff 0 and no contribution,
    so nothing downstream can show it as 0.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str  # e.g. "cj_stock_g7"
    family: str  # a demand family (cj_stock, shp_inv) or an input family (trends, ads)
    source: str | None  # sources.key; None while no source feeds it
    weight: float = Field(ge=0)  # from the score's config
    weight_eff: float = 0.0  # renormalised over the present inputs
    raw: float | None = None
    z: float | None = None
    normalization: Normalization | None = None  # where z's median and MAD came from
    contribution: float | None = None  # weight_eff × z: this input's share of the value
    as_of: AwareDatetime | None = None  # the input's newest capture
    missing: bool = False
    gap: bool = False  # the input's window had a coverage gap
    ai_derived: bool = False  # built from AI-extracted structured facts (DEC-047)
    prompt_version: str | None = None

    @model_validator(mode="after")
    def _ai_facts_name_their_prompt(self) -> Self:
        if self.ai_derived and not self.prompt_version:
            raise ValueError("an ai_derived input needs its prompt_version (DEC-047)")
        return self


class Penalty(BaseModel):
    """Points taken off after the weighted inputs: Trend's saturation penalty.

    Missing, it takes nothing off and is named in `missing` after the components.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str  # e.g. "saturation"
    source: str | None  # sources.key of its input; None while no source feeds it
    raw: float | None = None  # the input, e.g. Saturation 0–100
    points: float | None = Field(default=None, ge=0)  # taken off the score; None when missing
    missing: bool = False


class Explanation(BaseModel):
    """`scores.explanation`: every input, the missing ones by name, and the weight present."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_version: str
    config_digest: str  # the config's full SHA-256; model_version keeps 12 hex
    components: tuple[Component, ...]
    missing: tuple[str, ...]  # the missing components', then penalties', names
    coverage: float = Field(ge=0, le=1)  # present configured weight / all configured weight
    panel_size: int | None = Field(default=None, ge=0)  # Saturation: stores tracked since t−28
    penalties: tuple[Penalty, ...] = ()  # Trend: points off after the weighted inputs
    reason: str | None = None  # why the value is NULL, the Lifecycle rule or Opportunity's cap
    pending: Stage | None = None  # Lifecycle: tonight's stage, shown once a 2nd night matches
    confidence: float | None = Field(default=None, ge=0, le=1)  # Opportunity: coverage − cautions
    cautions: tuple[str, ...] = ()  # Opportunity: what lowered confidence, e.g. duty_not_set

    @model_validator(mode="after")
    def _missing_names_the_missing_inputs(self) -> Self:
        names = [c.name for c in self.components if c.missing]
        if self.missing != (*names, *(p.name for p in self.penalties if p.missing)):
            raise ValueError("missing must name exactly the missing inputs, in order")
        return self


def version(config: DataclassInstance) -> tuple[str, str]:
    """(model_version, digest) of a frozen config dataclass with a `revision` field.

    The FEATURE_VERSION rule (pulso_ml.features.demand): `{revision:03d}-{sha256[:12]}` of the
    sorted-key JSON, so any config change makes a new version and versions sort by revision.
    Bump `revision` with any change to a score's maths.
    """
    fields = asdict(config)
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()
    return f"{fields['revision']:03d}-{digest[:12]}", digest


def explain(
    config: DataclassInstance, components: Sequence[Component]
) -> tuple[float | None, Explanation]:
    """DEC-040: a missing input gets weight 0 and the present ones rescale to sum to 1.

    Returns Σ weight_eff × z over the present inputs, None when none is present (the score's
    value is then NULL, never 0), and the explanation. A score that maps that sum onto 0–100
    linearly (Trend and Saturation: 50 + 50 × sum / 3) gets each input's points by the same
    factor × its contribution.
    """
    total = sum(c.weight for c in components)
    present = sum(c.weight for c in components if not c.missing)
    renormalised = []
    for c in components:
        if c.missing or not present:
            renormalised.append(c.model_copy(update={"weight_eff": 0.0, "contribution": None}))
            continue
        if c.z is None:
            raise ValueError(f"{c.name} is present without a z")
        weight_eff = c.weight / present
        renormalised.append(
            c.model_copy(update={"weight_eff": weight_eff, "contribution": weight_eff * c.z})
        )
    model_version, digest = version(config)
    explanation = Explanation(
        model_version=model_version,
        config_digest=digest,
        components=tuple(renormalised),
        missing=tuple(c.name for c in components if c.missing),
        coverage=present / total if total else 0.0,
    )
    value = sum(c.contribution or 0.0 for c in renormalised) if present else None
    return value, explanation


class ScoreRow(NamedTuple):
    """One `scores` row to append; its model_version is the explanation's."""

    product_id: UUID
    date: date_type  # the UTC day scored, from inputs captured before date+1 00:00Z (DEC-031)
    kind: Kind
    value: float | None  # 0–100, stored to 0.1; None: every input missing, or `reason`
    explanation: Explanation
    stage: Stage | None = None  # lifecycle only, which has no value


def write(session: Session, rows: Sequence[ScoreRow]) -> int:
    """Appends rows and returns how many were new; the caller commits.

    A key already written keeps its row untouched, so re-running a night inserts nothing and a
    config change appends under its new model_version (DEC-040).
    """
    if not rows:
        return 0
    values = [
        {
            "product_id": row.product_id,
            "date": row.date,
            "kind": row.kind,
            "model_version": row.explanation.model_version,
            "value": row.value,
            "stage": row.stage,
            "explanation": row.explanation.model_dump(mode="json"),
        }
        for row in rows
    ]
    statement = insert(Score).on_conflict_do_nothing().returning(Score.id)
    return len(session.scalars(statement, values).all())


def latest(kind: Kind) -> Select[tuple[Score]]:
    """Each product's newest `kind` row: its latest date, then its newest computation.

    Callers add filters or joins. A backward scan of the unique key serves it.
    """
    return (
        select(Score)
        .where(Score.kind == kind)
        .order_by(
            Score.product_id.desc(),
            Score.date.desc(),
            Score.computed_at.desc(),
            Score.model_version.desc(),
        )
        .distinct(Score.product_id)
    )
