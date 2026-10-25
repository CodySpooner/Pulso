"""Google popular (P2-29 b, DEC-267, DEC-272): the owner's weekly Merchant Center Popular products
report, one country × category × week at a time, big brands hidden. Google allows internal use
only, so no public page may ever show these rows (DEC-267 f)."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, Field, TypeAdapter, ValidationError
from sqlalchemy import Row, func, or_, select
from sqlalchemy.sql import ColumnElement

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB
from pulso_core.models import PopularProduct, Source
from pulso_sources.merchant_bestsellers import gtin_tokens, link_products

router = APIRouter(prefix="/v1/popular-products", dependencies=[Depends(current_principal)])
COUNTRY = "US"  # v1 is the US market (SPEC §1)
# A brand with this many rows in one report (week × category) is a major brand, hidden by default:
# a dropshippable item is rarely one of a dozen ranked products under one brand (DEC-272 b).
MAJOR_BRAND_ROWS = 10
STALE_DAYS = 14  # Google says new data can take up to 2 weeks (DEC-267)
WEEK = timedelta(days=7)
CURSOR = TypeAdapter(int)
P = PopularProduct


class RankChange(BaseModel):
    """Places moved since the previous week, positive when it moved up. Null when the product is
    new or no earlier week is imported: never 0 (DEC-040)."""

    value: int | None
    basis: Literal["previous_rank", "previous_week", "new", "no_previous_week"]
    previous_rank: int | None
    as_of: date | None  # the week compared against; null when it isn't imported


class PopularRow(BaseModel):
    rank: int
    change: RankChange
    title: str
    brand: str | None
    major_brand: bool
    availability: str | None  # In stock, Out of stock, Product suggestion or Brand suggestion
    price_min_minor: int | None
    price_max_minor: int | None
    currency: str | None  # null with no price: never assumed to be USD (DEC-267 b)
    gtins: list[str]  # as Google wrote them
    product_id: UUID | None  # the one live product sharing a valid GTIN, resolved now (DEC-267 c)
    as_of: date  # the report week's Monday
    raw_payload_id: int


class PopularPage(BaseModel):
    country: str
    category: str | None  # the report shown
    categories: list[str | None]  # the shown week's reports
    weeks: list[date]  # every imported report week, newest first
    rows: list[PopularRow]
    next_cursor: str | None = Field(description="Pass as `cursor` with the same filters.")
    total: int  # rows in the report
    hidden: int  # major-brand rows left out; 0 with include_major_brands
    major_brand_rows: int  # the threshold
    previous_week: date | None  # the imported week the change compares against
    source: str
    source_name: str
    captured_at: AwareDatetime | None  # the report's import
    as_of: date | None  # the report week; null when nothing matches
    stale: bool  # the report week started more than 14 days ago


def in_report(report: Row[Any]) -> list[ColumnElement[bool]]:
    """One capture of one report, in the unique key's column order so its index serves it."""
    return [
        P.source_id == report.source_id,
        P.country == COUNTRY,
        P.category.is_(None) if report.category is None else P.category == report.category,
        P.observed_for == report.observed_for,
        P.raw_payload_id == report.raw_payload_id,
        P.parser_version == report.parser_version,
    ]


@router.get("", response_model=PopularPage)
def list_popular_products(
    session: DB,
    week: Annotated[date | None, Query(description="A report week's Monday; the newest")] = None,
    category: Annotated[
        str | None, Query(max_length=500, description="The shown week's first by default")
    ] = None,
    include_major_brands: bool = False,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> PopularPage:
    after = 0
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid popular products cursor.") from None
    source = session.scalars(select(Source).where(Source.key == "merchant_bestsellers")).one()
    # The newest capture of each report: a file downloaded again, or a new parser, adds one.
    # ponytail: groups the country's rows per request (about 16,000 a week); a migration adding an
    # (source_id, country, observed_for) index when two years of weeks make this slow.
    reports: dict[tuple[date, str | None], Row[Any]] = {}
    for capture in session.execute(
        select(P.source_id, P.observed_for, P.category, P.raw_payload_id, P.parser_version)
        .add_columns(func.max(P.captured_at).label("captured_at"))
        .where(P.source_id == source.id, P.country == COUNTRY)
        .group_by(P.source_id, P.observed_for, P.category, P.raw_payload_id, P.parser_version)
        .order_by(func.max(P.captured_at), P.raw_payload_id, P.parser_version)
    ):
        reports[capture.observed_for, capture.category] = capture  # the newest wins
    weeks = sorted({w for w, _ in reports}, reverse=True)
    shown = week or (weeks[0] if weeks else None)
    categories = sorted((c for w, c in reports if w == shown), key=lambda c: (c is not None, c))
    chosen = category if category is not None else (categories[0] if categories else None)
    report = reports.get((shown, chosen)) if shown else None
    page: PopularPage = PopularPage(
        country=COUNTRY,
        category=chosen,
        categories=categories,
        weeks=weeks,
        rows=[],
        next_cursor=None,
        total=0,
        hidden=0,
        major_brand_rows=MAJOR_BRAND_ROWS,
        previous_week=None,
        source=source.key,
        source_name=source.name,
        captured_at=None,
        as_of=None,
        stale=False,
    )
    if report is None:
        return page

    brand = func.lower(P.brand)
    sizes = dict(
        session.execute(select(brand, func.count()).where(*in_report(report)).group_by(brand))
        .tuples()
        .all()
    )
    majors = {b for b, n in sizes.items() if b is not None and n >= MAJOR_BRAND_ROWS}
    query = select(P).where(*in_report(report), P.rank > after)
    if majors and not include_major_brands:
        query = query.where(or_(P.brand.is_(None), brand.not_in(majors)))
    found = session.scalars(query.order_by(P.rank).limit(limit + 1)).all()
    rows = found[:limit]

    # Weekly change (DEC-267 d): Google's previous rank, else last week's report of the same
    # category matched on title and brand.
    previous_week = report.observed_for - WEEK
    previous = reports.get((previous_week, report.category))
    earlier: dict[tuple[str, str | None], int] = {}
    if previous is not None and any(row.previous_rank is None for row in rows):
        titles = {row.title for row in rows}
        earlier = {
            (title, b): rank
            for title, b, rank in session.execute(
                select(P.title, P.brand, func.min(P.rank))
                .where(*in_report(previous), P.title.in_(titles))
                .group_by(P.title, P.brand)
            ).tuples()
        }
    linked = link_products(session, rows)

    def change(row: PopularProduct) -> RankChange:
        before, basis = row.previous_rank, "previous_rank"
        if before is None:
            if previous is None:
                return RankChange(
                    value=None, basis="no_previous_week", previous_rank=None, as_of=None
                )
            if (before := earlier.get((row.title, row.brand))) is None:
                return RankChange(value=None, basis="new", previous_rank=None, as_of=previous_week)
            basis = "previous_week"
        return RankChange(
            value=before - row.rank, basis=basis, previous_rank=before, as_of=previous_week
        )

    page.rows = [
        PopularRow(
            rank=row.rank,
            change=change(row),
            title=row.title,
            brand=row.brand,
            major_brand=row.brand is not None and row.brand.lower() in majors,
            availability=row.availability,
            price_min_minor=row.price_min_minor,
            price_max_minor=row.price_max_minor,
            currency=row.currency,
            gtins=gtin_tokens(row.gtins),
            product_id=linked[row.id],
            as_of=row.observed_for,
            raw_payload_id=row.raw_payload_id,
        )
        for row in rows
    ]
    page.next_cursor = str(rows[-1].rank) if len(found) > limit else None
    page.total = sum(sizes.values())
    page.hidden = 0 if include_major_brands else sum(sizes[b] for b in majors)
    page.previous_week = previous_week if previous is not None else None
    page.captured_at = report.captured_at
    page.as_of = report.observed_for
    page.stale = datetime.now(UTC).date() - report.observed_for > timedelta(days=STALE_DAYS)
    return page
