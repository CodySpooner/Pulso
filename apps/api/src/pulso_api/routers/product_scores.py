"""Product scores (SC-5, DEC-331): the stored market scores and the caller's Opportunity."""

import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import select, tuple_
from starlette.responses import RedirectResponse, Response

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.product_series import DAYS, Range
from pulso_api.routers.products import DB, CurrentPrincipal
from pulso_api.schemas.provenance import NoSource
from pulso_core.models import Product, Score, WorkspaceSettings, workspace_product_economics
from pulso_core.scores import Explanation, Stage, latest
from pulso_ml.scores import opportunity as op

router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
Kind = Literal["trend", "saturation", "lifecycle"]  # the kinds the nightly job writes (SC-6)
KINDS: tuple[Kind, ...] = get_args(Kind)
CURSOR = TypeAdapter(tuple[date, int])
NO_ROW = "No source yet: nothing has scored this product."


class StoredScore(BaseModel):
    kind: Kind
    day: date  # the UTC day scored (scores.date)
    value: float | None  # 0–100; null on a lifecycle row, or with explanation.reason
    stage: Stage | None  # lifecycle only
    model_version: str
    as_of: AwareDatetime  # its inputs were captured before this
    explanation: Explanation


class LatestScores(BaseModel):
    trend: StoredScore | NoSource
    saturation: StoredScore | NoSource
    lifecycle: StoredScore | NoSource


class Opportunity(BaseModel):
    """The caller's workspace's Opportunity, computed at read time and never stored (DEC-041)."""

    value: float | None  # 0–100; null with explanation.reason
    as_of: AwareDatetime | None  # its oldest present input
    explanation: Explanation


class ProductScores(BaseModel):
    id: UUID
    range: Range
    start: date | None  # the range's first UTC day; null for `all`
    latest: LatestScores
    opportunity: Opportunity
    history: list[StoredScore]  # in the range, newest day first, then the newest row
    next_cursor: str | None = Field(description="Pass as `cursor` for the next, older page.")


def stored(row: Score) -> StoredScore:
    read = op.stored(row)
    assert read is not None
    return StoredScore(
        kind=row.kind,
        day=row.date,
        value=read.value,
        stage=row.stage,
        model_version=row.model_version,
        as_of=read.as_of,
        explanation=Explanation.model_validate(row.explanation),
    )


@router.get(
    "/{product_id}/scores",
    response_model=ProductScores,
    responses={308: {"description": "Merged: the survivor's scores URL, query string kept."}},
)
def get_product_scores(
    product_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    session: DB,
    range: Range = "90d",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 90,
) -> Response | ProductScores:
    """Score history with explanations (SC-5): a NULL row keeps its reason, no row is no source
    yet, and Opportunity is the caller's workspace's, never a stored row (DEC-331)."""
    product = session.get(Product, product_id)
    if product is None:
        raise APIError(404, "not_found", "Product not found.")
    if product.merged_into_id is not None:  # like GET /v1/products/{id}/series
        query = f"?{request.url.query}" if request.url.query else ""
        return RedirectResponse(f"../{product.merged_into_id}/scores{query}", status_code=308)

    rows = {k: session.scalar(latest(k).where(Score.product_id == product.id)) for k in KINDS}
    view = workspace_product_economics.c
    economics = (
        session.execute(
            select(workspace_product_economics).where(
                view.workspace_id == principal.workspace_id, view.product_id == product.id
            )
        )
        .mappings()
        .one_or_none()
    )
    settings = session.get(WorkspaceSettings, principal.workspace_id)
    found = op.opportunity(
        op.stored(rows["trend"]),
        op.stored(rows["saturation"]),
        op.margin_of(economics, settings),
        datetime.now(UTC),
    )

    start = datetime.now(UTC).date() - timedelta(days=DAYS[range] - 1) if range in DAYS else None
    history = select(Score).where(Score.product_id == product.id, Score.kind.in_(KINDS))
    if start is not None:
        history = history.where(Score.date >= start)
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid score cursor.") from None
        history = history.where(tuple_(Score.date, Score.id) < after)
    page = session.scalars(
        history.order_by(Score.date.desc(), Score.id.desc()).limit(limit + 1)
    ).all()
    last = page[limit - 1] if len(page) > limit else None
    return ProductScores(
        id=product.id,
        range=range,
        start=start,
        latest=LatestScores(
            **{
                k: NoSource(value=None, reason=NO_ROW) if row is None else stored(row)
                for k, row in rows.items()
            }
        ),
        opportunity=Opportunity(
            value=found.value, as_of=found.as_of, explanation=found.explanation
        ),
        history=[stored(row) for row in page[:limit]],
        next_cursor=json.dumps([last.date.isoformat(), last.id]) if last else None,
    )
