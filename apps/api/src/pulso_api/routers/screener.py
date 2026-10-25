"""Screener (WF-1 part a, DEC-336): stock-screener filters and sorts over every live product,
keyset-paginated. Margin and Opportunity are the caller's workspace's; the rest is global market
data. A page runs the same number of queries whatever its size (imp-488). `?format=csv` exports
the whole filtered set in the requested sort through the JSON's own rows (DEC-345)."""

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import (
    ARRAY,
    Integer,
    Select,
    Uuid,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    true,
    tuple_,
)
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement, Subquery
from sqlalchemy.sql.selectable import LateralFromClause as Lateral
from starlette.responses import Response

from pulso_api.auth import current_principal
from pulso_api.csv_export import csv_response, major
from pulso_api.errors import APIError
from pulso_api.routers.product_scores import KINDS, NO_ROW
from pulso_api.routers.products import (
    DB,
    NO_PRICE,
    NO_SIGNAL,
    CurrentPrincipal,
    Incomplete,
    Margin,
    Velocity,
    best_feature,
    is_stale,
    margin_stat,
    velocity_stat,
)
from pulso_api.schemas.provenance import NoSource, Sourced, Stat
from pulso_core.models import (
    Category,
    Image,
    Listing,
    ListingSnapshot,
    Product,
    ProductDailyFeature,
    Score,
    ShippingOption,
    Source,
    Supplier,
    WorkspaceSettings,
    workspace_product_economics,
)
from pulso_core.scores import Explanation, Stage, latest
from pulso_ml.scores import opportunity as op

router = APIRouter(prefix="/v1/screener", dependencies=[Depends(current_principal)])
Bigint = Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]
Money = Annotated[int, Field(ge=0, le=2**63 - 1)]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Points = Annotated[float, Field(ge=0, le=100)]  # a 0–100 score
Stars = Annotated[int, Field(ge=0, le=500)]  # hundredths of a star: 460 is 4.6
Days = Annotated[int, Field(ge=0, le=2**31 - 1)]
SortKey = Literal[
    "trend",
    "opportunity",
    "margin_bps",
    "velocity",
    "acceleration",
    "saturation",
    "price",
    "supplier_rating",
    "ship_days_us",
]
CURSOR = TypeAdapter(tuple[int | float | None, UUID])  # [the sort value, null last; id]
NO_RATING = "No live supplier listing has a rating yet."
NO_SHIPPING = "No live supplier listing has a US delivery estimate yet."
NO_ACCELERATION = "No 7-day growth a week earlier in this family yet."
UNSCORED = "Insufficient signal."
# The results table's order (vault Features/Product Screener), then the rest of a row; money in
# dollars, margin in percent, rating in stars; as_of is the row's oldest metric (DEC-345).
SCREENER_CSV = (
    "id",
    "product",
    "category",
    "lifecycle",
    "velocity_7d",
    "velocity_grade",
    "acceleration",
    "trend",
    "saturation",
    "opportunity",
    "margin",
    "margin_pct",
    "price",
    "currency",
    "supplier_rating",
    "ship_days_us",
    "as_of",
    "stale",
)


class Filters(BaseModel):
    """A screen's conditions, all of which must hold (AND). A product without a filtered metric
    is out: a missing value is never read as 0 (DEC-040). Every bound is inclusive."""

    model_config = ConfigDict(extra="forbid")
    margin_bps_min: Bigint | None = None  # landed margin %, basis points: 4000 is 40 %
    margin_bps_max: Bigint | None = None
    velocity_min: Finite | None = None  # V7: units over 7 days, Discover's velocity
    velocity_max: Finite | None = None
    acceleration_min: Finite | None = None  # G7(t) − G7(t−7)
    acceleration_max: Finite | None = None
    saturation_min: Points | None = None
    saturation_max: Points | None = None
    price_min: Money | None = None  # USD minor units: the lowest live store price
    price_max: Money | None = None
    supplier_rating_min: Stars | None = None  # the best live supplier listing's rating
    supplier_rating_max: Stars | None = None
    ship_days_us_min: Days | None = None  # the fastest US quote's worst case, in days
    ship_days_us_max: Days | None = None
    risk_min: Points | None = None  # accepted, not applied: no risk score until Phase 5
    risk_max: Points | None = None
    lifecycle: Annotated[list[Stage], Field(min_length=1)] | None = None  # any of these stages
    category: Annotated[int, Field(ge=1, le=2**31 - 1)] | None = None  # a categories.id


# Filters' ranges, each a metric of the same name (risk aside); the sorts add trend, opportunity.
RANGES = (
    "margin_bps",
    "velocity",
    "acceleration",
    "saturation",
    "price",
    "supplier_rating",
    "ship_days_us",
)


class Acceleration(BaseModel):
    """Acc = G7(t) − G7(t−7) in the velocity's family and feature version (vault Velocity &
    Acceleration): Lifecycle's input, read from the same feature rows as the velocity."""

    value: float
    family: str
    source: str
    source_name: str
    as_of: AwareDatetime
    stale: bool


class LatestScore(BaseModel):
    """A product's newest stored row of a kind (DEC-331). Its full explanation is on
    GET /v1/products/{id}/scores."""

    value: float | None  # 0–100; null on a lifecycle row, or with `reason`
    stage: Stage | None  # lifecycle only
    day: date  # the UTC day scored
    model_version: str
    as_of: AwareDatetime  # its inputs were captured before this
    reason: str | None  # why the value (or stage) is null: insufficient signal


class OpportunityValue(BaseModel):
    """The caller's workspace's Opportunity, computed at read time (DEC-331)."""

    value: float | None  # 0–100; null with `reason`
    as_of: AwareDatetime | None  # its oldest present input
    confidence: float | None
    reason: str | None  # why it is null, or capped: "margin below your floor"
    missing: list[str]  # its missing inputs; risk until Phase 5


class ScreenerRow(BaseModel):
    id: UUID
    title: str
    image_url: str | None
    category: str | None
    currency: Literal["USD"]  # of the *_minor stats
    price_minor: Stat  # the lowest live USD store price
    margin: Margin | Incomplete  # Discover's best margin; margin_bps is the margin %
    velocity: Velocity | NoSource
    acceleration: Acceleration | NoSource
    supplier_rating: Stat  # hundredths of a star
    ship_days_us: Stat
    trend: LatestScore | NoSource
    saturation: LatestScore | NoSource
    lifecycle: LatestScore | NoSource
    opportunity: OpportunityValue


class ScreenerPage(BaseModel):
    items: list[ScreenerRow]
    next_cursor: str | None = Field(
        description="Pass as `cursor` with the same filters and sort for the next page."
    )
    # Filters given but not applied, each with why: risk_min and risk_max until Phase 5.
    unapplied: dict[str, Literal["phase_5"]]


def snapshot() -> Any:
    """A listing's latest snapshot, priced or not, as every listing stat reads it."""
    snap = ListingSnapshot
    return (
        select(snap)
        .where(snap.listing_id == Listing.id)
        .order_by(snap.captured_at.desc(), snap.id.desc())
        .limit(1)
        .lateral()
    )


def live(*where: ColumnElement[bool]) -> Select[Any]:
    """The product's live listings, for a lateral that keeps one row: value, at, raw, source."""
    return (
        select()
        .select_from(Listing)
        .where(Listing.product_id == Product.id, Listing.delisted_at.is_(None), *where)
    )


def cheapest() -> Lateral:
    """The lowest live USD store price (Discover's price_min_minor), with its snapshot."""
    snap = snapshot()
    return (
        live(Listing.store_id.is_not(None))
        .join(snap, true())
        .add_columns(
            snap.c.price_min_minor.label("value"),
            snap.c.captured_at.label("at"),
            snap.c.raw_payload_id.label("raw"),
            Listing.source_id,
        )
        .where(snap.c.currency == "USD", snap.c.price_min_minor.is_not(None))
        .order_by(snap.c.price_min_minor, snap.c.captured_at.desc())
        .limit(1)
        .lateral("price")
    )


def best_rated() -> Lateral:
    """The best rating among live supplier listings, as the Suppliers tab reads each: the latest
    snapshot's, else the supplier's own as of the listing's last sighting."""
    snap = snapshot()
    stars = func.coalesce(snap.c.rating, Supplier.rating)
    observed = snap.c.rating.is_not(None)
    return (
        live()
        .join(Supplier, Supplier.id == Listing.supplier_id)
        .outerjoin(snap, true())
        .add_columns(
            cast(stars * 100, Integer).label("value"),
            case((observed, snap.c.captured_at), else_=Listing.last_seen_at).label("at"),
            case((observed, snap.c.raw_payload_id)).label("raw"),
            Listing.source_id,
        )
        .where(stars.is_not(None))
        .order_by(stars.desc(), Listing.id)
        .limit(1)
        .lateral("rating")
    )


def fastest() -> Lateral:
    """The fewest worst-case days among live supplier listings' US quotes at quantity 1, each
    listing's from its latest quoted day only, so a dropped method doesn't linger."""
    quote, same = ShippingOption, aliased(ShippingOption)
    day = (
        select(func.max(same.observed_for))
        .where(same.listing_id == Listing.id, same.destination_country == "US", same.quantity == 1)
        .scalar_subquery()
    )
    return (
        live(Listing.supplier_id.is_not(None))
        .join(quote, quote.listing_id == Listing.id)
        .add_columns(
            quote.max_days.label("value"),
            quote.captured_at.label("at"),
            quote.raw_payload_id.label("raw"),
            Listing.source_id,
        )
        .where(
            quote.destination_country == "US",
            quote.quantity == 1,
            quote.max_days.is_not(None),
            quote.observed_for == day,
        )
        .order_by(quote.max_days, quote.captured_at.desc(), quote.id.desc())
        .limit(1)
        .lateral("ship")
    )


def feature() -> Lateral:
    return best_feature(Product.id).add_columns(ProductDailyFeature.feature_version).lateral()


def acceleration(row: Lateral) -> ColumnElement[float]:
    week = aliased(ProductDailyFeature)
    before = select(week.growth_7d).where(
        week.product_id == Product.id,
        week.family == row.c.family,
        week.feature_version == row.c.feature_version,
        week.feature_date == row.c.feature_date - 7,
    )
    return (row.c.growth - before.scalar_subquery()).label("acceleration")


def universe(workspace_id: UUID, needed: set[str]) -> Subquery:
    """Every product Discover lists (neither merged nor emptied, DEC-271), with each needed
    metric's value: a lateral is joined only when a filter or the sort reads it."""
    query = (
        select(Product.id, Product.category_id)
        .select_from(Product)  # every join below hangs off it
        .where(Product.merged_into_id.is_(None), Product.status != "empty")
    )
    if needed & {"velocity", "acceleration"}:
        row = feature()
        query = query.outerjoin(row, true()).add_columns(
            row.c.velocity_7d.label("velocity"), acceleration(row)
        )
    for kind in KINDS:
        if kind in needed:
            score = latest(kind).where(Score.product_id == Product.id).limit(1).lateral(kind)
            column = score.c.stage if kind == "lifecycle" else score.c.value
            query = query.outerjoin(score, true()).add_columns(column.label(kind))
    for key, lateral in (("price", cheapest), ("supplier_rating", best_rated)):
        if key in needed:
            found = lateral()
            query = query.outerjoin(found, true()).add_columns(found.c.value.label(key))
    if "ship_days_us" in needed:
        found = fastest()
        query = query.outerjoin(found, true()).add_columns(found.c.value.label("ship_days_us"))
    if "margin_bps" in needed:  # R-16: an incomplete row's margin_bps is NULL
        view = workspace_product_economics.c
        query = query.outerjoin(
            workspace_product_economics,
            and_(view.product_id == Product.id, view.workspace_id == workspace_id),
        ).add_columns(view.margin_bps)
    return query.subquery("screen")


def conditions(screen: Subquery, filters: Filters) -> list[ColumnElement[bool]]:
    """SQL comparisons, so a NULL (missing) value fails every one of them."""
    where = []
    for key in RANGES:
        low, high = getattr(filters, f"{key}_min"), getattr(filters, f"{key}_max")
        if low is not None:
            where.append(screen.c[key] >= low)
        if high is not None:
            where.append(screen.c[key] <= high)
    if filters.lifecycle is not None:
        where.append(screen.c.lifecycle.in_(filters.lifecycle))
    if filters.category is not None:
        where.append(screen.c.category_id == filters.category)
    return where


def needed(filters: Filters, sort: SortKey) -> set[str]:
    keys = {key for key in RANGES if getattr(filters, f"{key}_min") is not None}
    keys |= {key for key in RANGES if getattr(filters, f"{key}_max") is not None}
    if filters.lifecycle is not None:
        keys.add("lifecycle")
    return keys if sort == "opportunity" else keys | {sort}  # Opportunity sorts in Python


def economics(
    session: Session, workspace_id: UUID, products: list[UUID] | Select[tuple[UUID]]
) -> dict[UUID, RowMapping]:
    """The workspace's workspace_product_economics rows, one query (imp-488's margin read)."""
    view = workspace_product_economics.c
    rows = session.execute(
        select(workspace_product_economics).where(
            view.workspace_id == workspace_id, view.product_id.in_(products)
        )
    ).mappings()
    return {row["product_id"]: row for row in rows}


def opportunity_of(
    trend: Score | None,
    saturation: Score | None,
    row: RowMapping | None,
    settings: WorkspaceSettings | None,
) -> op.Opportunity:
    return op.opportunity(op.stored(trend), op.stored(saturation), op.margin_of(row, settings))


@router.get(
    "",
    response_model=ScreenerPage,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "JSON, or with format=csv every matching product as a CSV download; "
            "an X-Unapplied header names the unapplied filters, as `unapplied` does.",
        },
    },
)
def screen_products(
    principal: CurrentPrincipal,
    session: DB,
    filters: Annotated[
        str | None,
        Query(max_length=4000, description="A JSON `Filters` object, as a saved screen holds."),
    ] = None,
    sort: SortKey = "trend",
    order: Literal["desc", "asc"] = "desc",
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    format: Annotated[
        Literal["json", "csv"],
        Query(description="csv: every matching product in this sort, no cursor or limit (DEC-345)"),
    ] = "json",
) -> ScreenerPage | Response:
    """Every product neither merged nor emptied that meets `filters`, sorted with missing values
    last in either order and then by id, keyset-paginated (DEC-336)."""
    try:
        given = Filters.model_validate_json(filters or "{}")
    except ValidationError:
        raise APIError(422, "invalid_filters", "Invalid screener filters.") from None
    after = None
    if cursor is not None and format == "json":
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid screener cursor.") from None
    workspace_id = principal.workspace_id
    screen = universe(workspace_id, needed(given, sort))
    matching = select(screen.c.id).where(*conditions(screen, given))
    settings = session.get(WorkspaceSettings, workspace_id)
    scores: dict[str, dict[UUID, Score]] = {}
    margins: dict[UUID, RowMapping] | None = None
    unapplied: dict[str, Literal["phase_5"]] = {
        name: "phase_5" for name in ("risk_min", "risk_max") if getattr(given, name) is not None
    }

    def export(query: Select[Any]) -> Response:
        response = csv_response(
            session,
            "screener",
            SCREENER_CSV,
            query,
            lambda chunk: csv_rows(session, workspace_id, settings, [row.id for row in chunk]),
        )
        if unapplied:
            response.headers["X-Unapplied"] = json.dumps(unapplied)
        return response

    if sort == "opportunity":
        # ponytail: Opportunity is Python (one landed-cost function, DEC-331), so the whole
        # filtered set is scored and sorted here; fine to a few thousand products, then
        # materialise per workspace (imp-279).
        scores = {kind: op.latest_rows(session, kind, matching) for kind in KINDS[:2]}
        margins = economics(session, workspace_id, matching)
        found = {
            product: opportunity_of(
                scores["trend"].get(product),
                scores["saturation"].get(product),
                margins.get(product),
                settings,
            ).value
            for product in session.scalars(matching)
        }

        def place(value: float | None, product: UUID) -> tuple[bool, float, int]:
            sign = -1 if order == "desc" else 1
            return value is None, sign * (value or 0), sign * product.int

        ranked = sorted(found, key=lambda product: place(found[product], product))
        if format == "csv":  # the ranking, in order, as a query the export can count and stream
            ids = func.unnest(literal(ranked, ARRAY(Uuid())))
            rank = ids.table_valued("id", with_ordinality="n").render_derived()
            return export(select(rank.c.id).order_by(rank.c.n))
        if after is not None:
            mark = place(None if after[0] is None else float(after[0]), after[1])
            ranked = [product for product in ranked if place(found[product], product) > mark]
        rows = [(found[product], product) for product in ranked[: limit + 1]]
    else:
        key, id_ = screen.c[sort], screen.c.id
        query = select(key, id_).where(*conditions(screen, given))
        if after is not None:
            value, after_id = after
            later = id_ < after_id if order == "desc" else id_ > after_id
            if value is None:
                query = query.where(key.is_(None), later)
            else:
                position = tuple_(key, id_)
                beyond = (
                    position < (value, after_id)
                    if order == "desc"
                    else position
                    > (
                        value,
                        after_id,
                    )
                )
                query = query.where(or_(beyond, key.is_(None)))
        ordered = (key.desc(), id_.desc()) if order == "desc" else (key.asc(), id_.asc())
        query = query.order_by(ordered[0].nulls_last(), ordered[1])
        if format == "csv":
            return export(query)
        rows = [(row[0], row[1]) for row in session.execute(query.limit(limit + 1))]
    page = [product for _, product in rows[:limit]]
    for kind in KINDS:  # the Opportunity sort has trend and saturation for the whole set
        if kind not in scores:
            scores[kind] = op.latest_rows(session, kind, page)
    if margins is None:
        margins = economics(session, workspace_id, page)
    next_cursor = None
    if len(rows) > limit:
        value, product = rows[limit - 1]
        value = float(value) if isinstance(value, Decimal) else value
        next_cursor = json.dumps([value, str(product)])
    return ScreenerPage(
        items=items(session, page, settings, scores, margins),
        next_cursor=next_cursor,
        unapplied=unapplied,
    )


def csv_rows(
    session: Session, workspace_id: UUID, settings: WorkspaceSettings | None, page: list[UUID]
) -> Iterator[list[object]]:
    """One export chunk as SCREENER_CSV cells: the same rows the JSON page builds."""
    scores: dict[str, dict[UUID, Score]] = {k: op.latest_rows(session, k, page) for k in KINDS}
    for row in items(session, page, settings, scores, economics(session, workspace_id, page)):
        velocity = row.velocity if isinstance(row.velocity, Velocity) else None
        margin = row.margin if isinstance(row.margin, Margin) else None
        rating = row.supplier_rating.value
        stats = (row.price_minor, row.margin, row.velocity, row.acceleration, row.supplier_rating,
                 row.ship_days_us, row.trend, row.saturation, row.lifecycle)  # fmt: skip
        yield [
            row.id,
            row.title,
            row.category,
            getattr(row.lifecycle, "stage", None),
            row.velocity.value,
            velocity.grade if velocity else None,
            row.acceleration.value,
            row.trend.value,
            row.saturation.value,
            row.opportunity.value,
            major(row.margin.value),
            Decimal(margin.margin_bps).scaleb(-2) if margin else None,  # 5275 bps is 52.75 %
            major(row.price_minor.value),
            row.currency,
            None if rating is None else Decimal(rating).scaleb(-2),  # 460 is 4.60 stars
            row.ship_days_us.value,
            min((s.as_of for s in stats if not isinstance(s, NoSource)), default=None),
            any(getattr(s, "stale", False) for s in stats),
        ]


def score_value(row: Score | None) -> LatestScore | NoSource:
    if row is None:
        return NoSource(value=None, reason=NO_ROW)
    read = op.stored(row)
    assert read is not None
    reason = None
    if read.value is None and row.stage is None:
        reason = Explanation.model_validate(row.explanation).reason or UNSCORED
    return LatestScore(
        value=read.value,
        stage=row.stage,
        day=row.date,
        model_version=row.model_version,
        as_of=read.as_of,
        reason=reason,
    )


def items(
    session: Session,
    page: list[UUID],
    settings: WorkspaceSettings | None,
    scores: dict[str, dict[UUID, Score]],
    margins: dict[UUID, RowMapping],
) -> list[ScreenerRow]:
    """The page's rows, a query per part whatever the page's size; the metrics come from the
    laterals the filters and sorts read, so a row shows the value it was screened on."""
    if not page:
        return []
    row, price, rating, ship = feature(), cheapest(), best_rated(), fastest()
    found = {
        each.id: each
        for each in session.execute(
            select(
                Product.id,
                Product.name,
                Image.url.label("image_url"),
                Category.path.label("category"),
                *row.c,
                acceleration(row),
                *(c.label(f"price_{c.name}") for c in price.c),
                *(c.label(f"rating_{c.name}") for c in rating.c),
                *(c.label(f"ship_{c.name}") for c in ship.c),
            )
            .select_from(Product)
            .outerjoin(row, true())
            .outerjoin(price, true())
            .outerjoin(rating, true())
            .outerjoin(ship, true())
            .outerjoin(Image, Image.id == Product.main_image_id)
            .outerjoin(Category, Category.id == Product.category_id)
            .where(Product.id.in_(page))
        )
    }
    sources = list(session.scalars(select(Source)))
    by_key = {source.key: source for source in sources}
    by_id = {source.id: source for source in sources}
    now = datetime.now(UTC)

    def traced(each: Any, name: str, reason: str) -> Stat:
        value = getattr(each, f"{name}_value")
        if value is None:
            return NoSource(value=None, reason=reason)
        source = by_id[getattr(each, f"{name}_source_id")]
        at = getattr(each, f"{name}_at")
        return Sourced(
            value=value,
            source=source.key,
            source_name=source.name,
            as_of=at,
            raw_payload_id=getattr(each, f"{name}_raw"),
            stale=is_stale(source.config, at, now),
        )

    rows = []
    for product in page:
        each = found[product]
        velocity = velocity_stat(each, by_key, now)
        accel: Acceleration | NoSource = NoSource(value=None, reason=NO_SIGNAL)
        if isinstance(velocity, Velocity):
            accel = NoSource(value=None, reason=NO_ACCELERATION)
            if each.acceleration is not None:
                accel = Acceleration(
                    value=each.acceleration,
                    **velocity.model_dump(include={"family", "source", "source_name", "as_of"}),
                    stale=velocity.stale,
                )
        trend, saturation = scores["trend"].get(product), scores["saturation"].get(product)
        chance = opportunity_of(trend, saturation, margins.get(product), settings)
        rows.append(
            ScreenerRow(
                id=product,
                title=each.name,
                image_url=each.image_url,
                category=each.category,
                currency="USD",
                price_minor=traced(each, "price", NO_PRICE),
                margin=margin_stat(margins.get(product), by_key, now),
                velocity=velocity,
                acceleration=accel,
                supplier_rating=traced(each, "rating", NO_RATING),
                ship_days_us=traced(each, "ship", NO_SHIPPING),
                trend=score_value(trend),
                saturation=score_value(saturation),
                lifecycle=score_value(scores["lifecycle"].get(product)),
                opportunity=OpportunityValue(
                    value=chance.value,
                    as_of=chance.as_of,
                    confidence=chance.explanation.confidence,
                    reason=chance.explanation.reason,
                    missing=list(chance.explanation.missing),
                ),
            )
        )
    return rows
