"""Amazon ranks (AMZ-1b, DEC-286): the owner's imported Best Sellers and Movers & Shakers lists
(DEC-279), each category × rank kind at its newest day by default. A rank only means something in
its own list, so rows are ordered and paged list by list and never ranked across lists."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import Row, func, literal, select, tuple_

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB
from pulso_core.models import AmazonRank, Source
from pulso_sources.merchant_bestsellers import link_products

# Global market data (no workspace_id), signed-in only like Google popular (DEC-272).
router = APIRouter(prefix="/v1/amazon", dependencies=[Depends(current_principal)])
STALE_DAYS = 14
A = AmazonRank
RankKind = Literal["bsr", "movers"]  # Best Sellers, Movers & Shakers (DEC-279)
CURSOR = TypeAdapter(tuple[str, str, int, str])  # the last row's category, rank kind, rank, ASIN


class AmazonList(BaseModel):
    """One category × rank kind at its newest imported day."""

    category: str
    rank_kind: RankKind
    as_of: date  # the newest day imported
    captured_at: AwareDatetime  # that day's newest import
    rows: int


class AmazonRankRow(BaseModel):
    asin: str
    title: str
    category: str
    rank_kind: RankKind
    rank: int  # within its category and rank kind only
    price_minor: int | None
    currency: str
    rating: float | None  # 0–5
    review_count: int | None
    product_id: UUID | None  # the one live product sharing a valid GTIN, resolved now (DEC-267 c)
    as_of: date  # observed_for: the day the ranks are from
    captured_at: AwareDatetime  # the import
    raw_payload_id: int


class AmazonRankPage(BaseModel):
    source: str | None  # null when the amazon source row is missing: no source yet
    source_name: str | None
    lists: list[AmazonList]  # every category × rank kind, unfiltered, for the filters
    rows: list[AmazonRankRow]  # by category, rank kind, then rank
    next_cursor: str | None = Field(description="Pass as `cursor` with the same filters.")
    total: int  # rows in the shown lists
    as_of: date | None  # the shown lists' newest day; null when nothing matches
    captured_at: AwareDatetime | None  # the shown lists' newest import
    stale: bool  # the shown lists' newest day is over 14 days old; never with observed_for


@router.get("/ranks", response_model=AmazonRankPage)
def list_amazon_ranks(
    session: DB,
    category: Annotated[str | None, Query(max_length=500)] = None,
    rank_kind: RankKind | None = None,
    observed_for: Annotated[
        date | None, Query(description="That day's lists; each list's newest day by default")
    ] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> AmazonRankPage:
    after = None
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid Amazon ranks cursor.") from None
    source = session.scalars(select(Source).where(Source.key == "amazon")).one_or_none()
    page = AmazonRankPage(
        source=source.key if source else None,
        source_name=source.name if source else None,
        lists=[],
        rows=[],
        next_cursor=None,
        total=0,
        as_of=None,
        captured_at=None,
        stale=False,
    )
    # The newest capture of each list and day: a corrected file imported again adds one.
    # ponytail: groups the whole table per request (one row per ranked ASIN and day); a migration
    # adding a (category, rank_kind, observed_for) index when imports make this slow.
    captures: dict[tuple[str, str, date], Row[Any]] = {}
    for capture in session.execute(
        select(A.category, A.rank_kind, A.observed_for, A.raw_payload_id, A.parser_version)
        .add_columns(func.max(A.captured_at).label("captured_at"), func.count().label("rows"))
        .group_by(A.category, A.rank_kind, A.observed_for, A.raw_payload_id, A.parser_version)
        .order_by(func.max(A.captured_at), A.raw_payload_id, A.parser_version)
    ):
        captures[capture.category, capture.rank_kind, capture.observed_for] = capture  # newest wins
    newest = {key[:2]: captures[key] for key in sorted(captures)}  # the newest day wins
    page.lists = [
        AmazonList(
            category=c.category,
            rank_kind=c.rank_kind,
            as_of=c.observed_for,
            captured_at=c.captured_at,
            rows=c.rows,
        )
        for c in (newest[key] for key in sorted(newest))
    ]
    shown = [
        c
        for (cat, kind, day), c in captures.items()
        if category in (None, cat)
        and rank_kind in (None, kind)
        and (day == observed_for if observed_for else c is newest[cat, kind])
    ]
    if not shown:
        return page

    order = (A.category, A.rank_kind, A.rank, A.asin)
    query = select(A).where(
        tuple_(A.category, A.rank_kind, A.observed_for, A.raw_payload_id, A.parser_version).in_(
            [
                (c.category, c.rank_kind, c.observed_for, c.raw_payload_id, c.parser_version)
                for c in shown
            ]
        )
    )
    if after is not None:
        query = query.where(tuple_(*order) > tuple_(*map(literal, after)))
    found = session.scalars(query.order_by(*order).limit(limit + 1)).all()
    rows = found[:limit]
    linked = link_products(session, rows)
    page.rows = [
        AmazonRankRow(
            asin=row.asin,
            title=row.title,
            category=row.category,
            rank_kind=row.rank_kind,  # the import allows only bsr and movers
            rank=row.rank,
            price_minor=row.price_minor,
            currency=row.currency,
            rating=None if row.rating is None else float(row.rating),
            review_count=row.review_count,
            product_id=linked[row.id],
            as_of=row.observed_for,
            captured_at=row.captured_at,
            raw_payload_id=row.raw_payload_id,
        )
        for row in rows
    ]
    if len(found) > limit:
        last = rows[-1]
        page.next_cursor = CURSOR.dump_json(
            (last.category, last.rank_kind, last.rank, last.asin)
        ).decode()
    page.total = sum(c.rows for c in shown)
    page.as_of = max(c.observed_for for c in shown)
    page.captured_at = max(c.captured_at for c in shown)
    page.stale = observed_for is None and datetime.now(UTC).date() - page.as_of > timedelta(
        days=STALE_DAYS
    )
    return page
