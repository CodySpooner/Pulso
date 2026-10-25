"""Google popular (P2-29 b, DEC-267, DEC-272): the owner's weekly Merchant Center Popular products
report, one country × category × week at a time, big brands hidden, plus the workspace's own
brand list (DEC-277). Google allows internal use only, so no public page may ever show these rows
(DEC-267 f)."""

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy import Row, delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import ColumnElement

from pulso_api.auth import Principal, current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB
from pulso_core.models import PopularBrandRule, PopularProduct, Source
from pulso_sources.merchant_bestsellers import gtin_tokens, link_products

router = APIRouter(prefix="/v1/popular-products", dependencies=[Depends(current_principal)])
COUNTRY = "US"  # v1 is the US market (SPEC §1)
# A brand with this many rows in one report (week × category) is a major brand, hidden by default:
# a dropshippable item is rarely one of a dozen ranked products under one brand (DEC-272 b).
MAJOR_BRAND_ROWS = 10
STALE_DAYS = 14  # Google says new data can take up to 2 weeks (DEC-267)
WEEK = timedelta(days=7)
CURSOR = TypeAdapter(int)
BRAND_CURSOR = TypeAdapter(str)
P = PopularProduct
R = PopularBrandRule
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
Brand = Annotated[str, StringConstraints(min_length=1, max_length=500)]


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
    major_brand: bool  # the brand has MAJOR_BRAND_ROWS or more rows in this report
    # Why the default view leaves the row out: the major-brand rule, or your hide rule (DEC-277).
    hidden_by: Literal["major", "you"] | None
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
    hidden: int  # rows left out, major brands' and yours; 0 with include_major_brands
    hidden_by_you: int  # of those, rows your hidden brands left out
    major_brand_rows: int  # the threshold
    previous_week: date | None  # the imported week the change compares against
    source: str
    source_name: str
    captured_at: AwareDatetime | None  # the report's import
    as_of: date | None  # the report week; null when nothing matches
    stale: bool  # the newest imported week started more than 14 days ago


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
    principal: CurrentPrincipal,
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
        hidden_by_you=0,
        major_brand_rows=MAJOR_BRAND_ROWS,
        previous_week=None,
        source=source.key,
        source_name=source.name,
        captured_at=None,
        as_of=None,
        stale=bool(weeks) and datetime.now(UTC).date() - weeks[0] > timedelta(days=STALE_DAYS),
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
    rules = dict(
        session.execute(
            select(R.brand_norm, R.action).where(
                R.workspace_id == principal.workspace_id,
                R.brand_norm.in_([b for b in sizes if b is not None]),
            )
        )
        .tuples()
        .all()
    )
    # A show rule exempts a major brand; a hide rule hides any brand (DEC-277).
    hidden_by: dict[str, Literal["major", "you"]] = {
        **{b: "major" for b in majors if rules.get(b) != "show"},
        **{b: "you" for b, action in rules.items() if action == "hide"},
    }
    query = select(P).where(*in_report(report), P.rank > after)
    if hidden_by and not include_major_brands:
        query = query.where(or_(P.brand.is_(None), brand.not_in(hidden_by)))
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
            hidden_by=hidden_by.get(row.brand.lower()) if row.brand is not None else None,
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
    if not include_major_brands:
        page.hidden = sum(sizes[b] for b in hidden_by)
        page.hidden_by_you = sum(sizes[b] for b, why in hidden_by.items() if why == "you")
    page.previous_week = previous_week if previous is not None else None
    page.captured_at = report.captured_at
    page.as_of = report.observed_for
    return page


# The workspace's brand list (DEC-277): current preference, so a rule is replaced or deleted in
# place. Brands match as the major-brand rule reads them, lower(brand).
class BrandRuleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand: Brand  # as Google wrote it on a row
    action: Literal["hide", "show"]  # show exempts a major brand from MAJOR_BRAND_ROWS


class BrandRule(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    brand: str  # the spelling last hidden or shown
    action: Literal["hide", "show"]
    created_at: AwareDatetime  # when this action was set


class BrandRulePage(BaseModel):
    items: list[BrandRule]  # by brand, case-insensitive
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


@router.get("/brands", response_model=BrandRulePage)
def list_popular_brand_rules(
    principal: CurrentPrincipal,
    session: DB,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> BrandRulePage:
    query = select(R).where(R.workspace_id == principal.workspace_id)
    if cursor is not None:
        try:
            query = query.where(R.brand_norm > BRAND_CURSOR.validate_json(cursor))
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid brand rule cursor.") from None
    found = session.scalars(query.order_by(R.brand_norm).limit(limit + 1)).all()
    last = found[limit - 1] if len(found) > limit else None
    return BrandRulePage(
        items=[BrandRule.model_validate(rule) for rule in found[:limit]],
        next_cursor=BRAND_CURSOR.dump_json(last.brand_norm).decode() if last else None,
    )


@router.put("/brands", response_model=BrandRule)
def put_popular_brand_rule(
    body: BrandRuleIn, principal: CurrentPrincipal, session: DB
) -> BrandRule:
    """Hide or show a brand for this workspace, replacing its earlier rule."""
    statement = insert(R).values(
        workspace_id=principal.workspace_id,
        brand_norm=func.lower(body.brand),
        brand=body.brand,
        action=body.action,
        created_by=principal.user_id,
    )
    rule = session.scalars(
        statement.on_conflict_do_update(
            index_elements=[R.workspace_id, R.brand_norm],
            set_={
                "brand": statement.excluded.brand,
                "action": statement.excluded.action,
                "created_by": statement.excluded.created_by,
                "created_at": func.now(),
            },
        ).returning(R)
    ).one()
    saved = BrandRule.model_validate(rule)
    session.commit()
    return saved


@router.delete("/brands", response_model=BrandRule | None)
def delete_popular_brand_rule(
    brand: Annotated[Brand, Query()], principal: CurrentPrincipal, session: DB
) -> BrandRule | None:
    """Forget this workspace's rule for the brand: the major-brand rule applies again. Returns
    the rule removed, or null when there was none."""
    rule = session.scalars(
        delete(R)
        .where(R.workspace_id == principal.workspace_id, R.brand_norm == func.lower(brand))
        .returning(R)
    ).one_or_none()
    removed = BrandRule.model_validate(rule) if rule else None
    session.commit()
    return removed
