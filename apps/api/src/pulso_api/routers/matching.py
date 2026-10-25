"""Matching Queue admin API (UX-1, DEC-263): pending pairs, one pair side by side, and the owner's
decisions through pulso_ml.matching.decisions. Match tables are global market data; the impact
sort and the notes and tags counts are the workspace's own."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from sqlalchemy import and_, exists, false, func, select, tuple_
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session, aliased
from sqlalchemy.sql import ColumnElement

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.routers.products import with_merged
from pulso_core.models import (
    Image,
    Listing,
    ListingSnapshot,
    ListingVariant,
    MatchCandidate,
    MatchDecision,
    Product,
    ProductNote,
    ProductTag,
    Source,
    Store,
    Supplier,
)
from pulso_core.settings import Settings, get_settings
from pulso_ml.matching import decisions
from pulso_ml.matching.matcher import canonical, redirects
from pulso_ml.matching.score import CONFIG

router = APIRouter(prefix="/v1/admin/matching", dependencies=[Depends(current_principal)])
DB = Annotated[Session, Depends(get_db)]
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
CURSOR = TypeAdapter(tuple[bool, Decimal, int])
MEMBERS = 48  # cluster strip thumbnails; `listings` carries the full count
REASON = "Matching Queue"


class Thresholds(BaseModel):
    """The current scorer (DEC-249): a pair at `auto_link` or above with a sane price links."""

    version: str
    auto_link: float
    queue: float
    image_weight: float
    title_weight: float
    phash_weight: float
    markup_low: float  # retail ÷ supplier cost must sit in [markup_low, markup_high]
    markup_high: float


THRESHOLDS = Thresholds(
    version=CONFIG.version,
    auto_link=float(CONFIG.auto),
    queue=float(CONFIG.queue),
    image_weight=float(CONFIG.image_weight),
    title_weight=float(CONFIG.title_weight),
    phash_weight=float(CONFIG.phash_weight),
    markup_low=float(CONFIG.markup_low),
    markup_high=float(CONFIG.markup_high),
)


class Side(BaseModel):
    listing_id: int
    title: str
    source: str  # sources.key
    image_url: str | None  # the lowest-position image
    product_id: UUID | None


class QueueItem(BaseModel):
    id: int
    score: float
    scorer_version: str
    created_at: AwareDatetime
    impact: bool  # this workspace has notes or tags on either side's product
    a: Side
    b: Side


class QueueSummary(BaseModel):
    pending: int  # every queued pair, before filters
    stored_sources: list[str]  # sources with a stored listing; matching needs two
    auto_linked: int  # listings the matcher linked
    last_auto_link_at: AwareDatetime | None
    matcher_enabled: bool  # MATCHER_ENABLED: off, nothing new queues


class Facets(BaseModel):
    source_pairs: list[str]  # "cj+shopify_stores", over every queued pair
    versions: list[str]


class QueuePage(BaseModel):
    items: list[QueueItem]
    next_cursor: str | None = Field(
        description="Pass as `cursor` with the same sort and filters for the next page."
    )
    summary: QueueSummary
    facets: Facets
    thresholds: Thresholds


class Price(BaseModel):
    min_minor: int | None
    max_minor: int | None
    currency: str
    captured_at: AwareDatetime


class ListingDetail(BaseModel):
    id: int
    title: str
    url: str
    source: str
    source_name: str
    vendor: str | None  # the store's domain or the supplier's name
    vendor_kind: Literal["store", "supplier"] | None
    images: list[str]  # up to four, by position
    price: Price | None  # the latest snapshot
    variants: int
    first_seen_at: AwareDatetime
    delisted_at: AwareDatetime | None
    product_id: UUID | None


class Member(BaseModel):
    listing_id: int
    title: str
    source: str
    vendor: str | None
    image_url: str | None


class Cluster(BaseModel):
    """A side's product: what a merge moves (listings) and what stays and follows (notes, tags)."""

    product_id: UUID
    name: str
    first_seen_at: AwareDatetime
    listings: int
    members: list[Member]  # the first 48 by listing id
    notes: int  # this workspace's, on the product and products merged into it
    tags: int


class CandidateDetail(BaseModel):
    id: int
    status: str
    superseded: bool  # decided, or both sides already on one product: the queue skips it
    score: float
    scorer_version: str
    image_cos: float | None
    title_cos: float | None
    phash_sim: float | None
    price_sane: bool | None
    created_at: AwareDatetime
    a: ListingDetail
    b: ListingDetail
    clusters: list[Cluster]  # one per side product, a's first
    thresholds: Thresholds


class Pair(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["accept", "reject"]
    candidate_id: int
    reason: str | None = Field(default=None, max_length=500)


class Merge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["merge"]
    product_id: UUID
    into: UUID
    reason: str | None = Field(default=None, max_length=500)


class Move(BaseModel):
    """Split moves listings of one product onto `into` or a new product; unlink frees them."""

    model_config = ConfigDict(extra="forbid")
    action: Literal["split", "unlink"]
    listing_ids: Annotated[list[int], Field(min_length=1, max_length=500)]
    into: UUID | None = None
    reason: str | None = Field(default=None, max_length=500)


class Decision(BaseModel):
    id: int | None = Field(description="Pass to undo. Null when the decision moved nothing.")
    action: str
    product_id: UUID | None  # where the pair or listings now sit
    listing_ids: list[int]  # every listing with a new decision row
    decided_at: AwareDatetime | None


def float_or_none(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def context_products(session: Session, workspace_id: UUID) -> set[UUID]:
    """Live products this workspace has notes or tags on."""
    touched = session.scalars(
        select(ProductNote.product_id)
        .where(ProductNote.workspace_id == workspace_id)
        .union(select(ProductTag.product_id).where(ProductTag.workspace_id == workspace_id))
    ).all()
    merged = redirects(session)
    return {root for product in touched if (root := canonical(merged, product)) is not None}


def first_image(listing_id: Any) -> Any:
    return (
        select(Image.url)
        .where(Image.listing_id == listing_id)
        .order_by(Image.position, Image.id)
        .limit(1)
        .scalar_subquery()
    )


@router.get("/candidates", response_model=QueuePage)
def list_match_candidates(
    session: DB,
    principal: CurrentPrincipal,
    settings: Annotated[Settings, Depends(get_settings)],
    sort: Literal["impact", "score", "age"] = "impact",
    source_pair: Annotated[str | None, Query(pattern=r"^[a-z0-9_]+\+[a-z0-9_]+$")] = None,
    min_score: Annotated[Decimal | None, Query(ge=0, le=1)] = None,
    max_score: Annotated[Decimal | None, Query(ge=0, le=1)] = None,
    version: Annotated[str | None, Query(max_length=80)] = None,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> QueuePage:
    """Pending pairs not already on one product, impact first by default, keyset-paginated.

    Impact is this workspace's context (notes or tags) on either side's product; watchlists,
    boards and tests join it when they exist (DEC-263 c).
    ponytail: the impact sort computes over every pending row; it is a small queue.
    """
    a, b = aliased(Listing), aliased(Listing)
    source_a, source_b = aliased(Source), aliased(Source)
    context = context_products(session, principal.workspace_id)
    # An expression even when empty (Postgres refuses a constant ORDER BY); NULL: no product.
    impact = func.coalesce(a.product_id.in_(context) | b.product_id.in_(context), false())
    low, high = func.least(source_a.key, source_b.key), func.greatest(source_a.key, source_b.key)
    queued: list[ColumnElement[bool]] = [
        MatchCandidate.status == "pending",
        ~and_(a.product_id.is_not(None), a.product_id.is_not_distinct_from(b.product_id)),
    ]

    def joined(*columns: Any) -> Any:
        return (
            select(*columns)
            .select_from(MatchCandidate)
            .join(a, a.id == MatchCandidate.listing_a_id)
            .join(b, b.id == MatchCandidate.listing_b_id)
            .join(source_a, source_a.id == a.source_id)
            .join(source_b, source_b.id == b.source_id)
            .where(*queued)
        )

    where: list[ColumnElement[bool]] = []
    if source_pair:
        first, second = sorted(source_pair.split("+"))
        where += [low == first, high == second]
    if min_score is not None:
        where.append(MatchCandidate.score >= min_score)
    if max_score is not None:
        where.append(MatchCandidate.score < max_score)
    if version:
        where.append(MatchCandidate.scorer_version == version)
    if cursor is not None:
        try:
            after_impact, after_score, after_id = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid candidate cursor.") from None
        if sort == "impact":
            where.append(
                tuple_(impact, MatchCandidate.score, MatchCandidate.id)
                < (after_impact, after_score, after_id)
            )
        elif sort == "score":
            where.append(tuple_(MatchCandidate.score, MatchCandidate.id) < (after_score, after_id))
        else:
            where.append(MatchCandidate.id > after_id)
    order = {
        "impact": (impact.desc(), MatchCandidate.score.desc(), MatchCandidate.id.desc()),
        "score": (MatchCandidate.score.desc(), MatchCandidate.id.desc()),
        "age": (MatchCandidate.id,),
    }[sort]
    rows = session.execute(
        joined(
            MatchCandidate,
            impact.label("impact"),
            *(
                column.label(f"{side}_{name}")
                for side, (listing, source) in (("a", (a, source_a)), ("b", (b, source_b)))
                for name, column in (
                    ("title", listing.title),
                    ("source", source.key),
                    ("image_url", first_image(listing.id)),
                    ("product_id", listing.product_id),
                )
            ),
        )
        .where(*where)
        .order_by(*order)
        .limit(limit + 1)
    ).all()

    def side(row: Any, key: str, listing_id: int) -> Side:
        values = {
            name: getattr(row, f"{key}_{name}")
            for name in Side.model_fields
            if name != "listing_id"
        }
        return Side(listing_id=listing_id, **values)

    items = [
        QueueItem(
            id=row.MatchCandidate.id,
            score=float(row.MatchCandidate.score),
            scorer_version=row.MatchCandidate.scorer_version,
            created_at=row.MatchCandidate.created_at,
            impact=row.impact,
            a=side(row, "a", row.MatchCandidate.listing_a_id),
            b=side(row, "b", row.MatchCandidate.listing_b_id),
        )
        for row in rows[:limit]
    ]
    last = rows[limit - 1] if len(rows) > limit else None
    pairs = session.execute(joined(low, high).distinct().order_by(low, high)).tuples().all()
    algo = session.execute(
        select(func.count(), func.max(MatchDecision.decided_at)).where(
            MatchDecision.actor == "algo", MatchDecision.action == "link"
        )
    ).one()
    return QueuePage(
        items=items,
        next_cursor=json.dumps(
            [bool(last.impact), str(last.MatchCandidate.score), last.MatchCandidate.id]
        )
        if last
        else None,
        summary=QueueSummary(
            pending=session.scalar(joined(func.count())) or 0,
            stored_sources=list(
                session.scalars(
                    select(Source.key)
                    .where(exists().where(Listing.source_id == Source.id))
                    .order_by(Source.key)
                )
            ),
            auto_linked=algo[0],
            last_auto_link_at=algo[1],
            matcher_enabled=settings.matcher_enabled,
        ),
        facets=Facets(
            source_pairs=[f"{x}+{y}" for x, y in pairs],
            versions=list(
                session.scalars(
                    joined(MatchCandidate.scorer_version)
                    .distinct()
                    .order_by(MatchCandidate.scorer_version)
                )
            ),
        ),
        thresholds=THRESHOLDS,
    )


def listing_detail(session: Session, listing_id: int) -> ListingDetail:
    row = session.execute(
        select(Listing, Source.key, Source.name, Store.domain, Supplier.name.label("supplier"))
        .join(Source, Source.id == Listing.source_id)
        .outerjoin(Store, Store.id == Listing.store_id)
        .outerjoin(Supplier, Supplier.id == Listing.supplier_id)
        .where(Listing.id == listing_id)
    ).one()
    listing: Listing = row.Listing
    snapshot = session.scalars(
        select(ListingSnapshot)
        .where(ListingSnapshot.listing_id == listing_id)
        .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
    ).first()
    images = session.scalars(
        select(Image.url)
        .where(Image.listing_id == listing_id)
        .order_by(Image.position, Image.id)
        .limit(4)
    ).all()
    return ListingDetail(
        id=listing.id,
        title=listing.title,
        url=listing.url,
        source=row.key,
        source_name=row.name,
        vendor=row.domain or row.supplier,
        vendor_kind="store" if row.domain else "supplier" if row.supplier else None,
        images=list(images),
        price=Price(
            min_minor=snapshot.price_min_minor,
            max_minor=snapshot.price_max_minor,
            currency=snapshot.currency,
            captured_at=snapshot.captured_at,
        )
        if snapshot
        else None,
        variants=session.scalar(select(func.count()).where(ListingVariant.listing_id == listing_id))
        or 0,
        first_seen_at=listing.first_seen_at,
        delisted_at=listing.delisted_at,
        product_id=listing.product_id,
    )


def cluster(session: Session, product_id: UUID, workspace_id: UUID) -> Cluster:
    product = session.get_one(Product, product_id)
    group = with_merged(product_id)
    members = session.execute(
        select(
            Listing.id,
            Listing.title,
            Source.key,
            Store.domain,
            Supplier.name,
            first_image(Listing.id),
        )
        .join(Source, Source.id == Listing.source_id)
        .outerjoin(Store, Store.id == Listing.store_id)
        .outerjoin(Supplier, Supplier.id == Listing.supplier_id)
        .where(Listing.product_id.in_(group))
        .order_by(Listing.id)
        .limit(MEMBERS)
    ).all()

    def count(model: type[ProductNote] | type[ProductTag]) -> int:
        return (
            session.scalar(
                select(func.count()).where(
                    model.workspace_id == workspace_id, model.product_id.in_(group)
                )
            )
            or 0
        )

    return Cluster(
        product_id=product.id,
        name=product.name,
        first_seen_at=product.first_seen_at,
        listings=session.scalar(select(func.count()).where(Listing.product_id.in_(group))) or 0,
        members=[
            Member(
                listing_id=row[0],
                title=row[1],
                source=row[2],
                vendor=row[3] or row[4],
                image_url=row[5],
            )
            for row in members
        ],
        notes=count(ProductNote),
        tags=count(ProductTag),
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateDetail)
def get_match_candidate(
    candidate_id: int, session: DB, principal: CurrentPrincipal
) -> CandidateDetail:
    candidate = session.get(MatchCandidate, candidate_id)
    if candidate is None:
        raise APIError(404, "not_found", "Candidate not found.")
    a = listing_detail(session, candidate.listing_a_id)
    b = listing_detail(session, candidate.listing_b_id)
    products = list(dict.fromkeys(p for p in (a.product_id, b.product_id) if p is not None))
    return CandidateDetail(
        id=candidate.id,
        status=candidate.status,
        superseded=candidate.status != "pending"
        or (a.product_id is not None and a.product_id == b.product_id),
        score=float(candidate.score),
        scorer_version=candidate.scorer_version,
        image_cos=float_or_none(candidate.image_cos),
        title_cos=float_or_none(candidate.title_cos),
        phash_sim=float_or_none(candidate.phash_sim),
        price_sane=candidate.price_sane,
        created_at=candidate.created_at,
        a=a,
        b=b,
        clusters=[cluster(session, p, principal.workspace_id) for p in products],
        thresholds=THRESHOLDS,
    )


def decided(session: Session, actor: str, action: str, product_id: UUID | None) -> Decision:
    """The rows this transaction wrote: one actor at one transaction time (DEC-263 b)."""
    rows = session.execute(
        select(MatchDecision.id, MatchDecision.listing_id, MatchDecision.decided_at)
        .where(MatchDecision.actor == actor, MatchDecision.decided_at == func.now())
        .order_by(MatchDecision.id)
    ).all()
    session.commit()
    return Decision(
        id=rows[0].id if rows else None,
        action=action,
        product_id=product_id,
        listing_ids=[row.listing_id for row in rows],
        decided_at=rows[0].decided_at if rows else None,
    )


@contextmanager
def refusals() -> Iterator[None]:
    """A service refusal is a 409 with its reason; a missing row is a 404."""
    try:
        yield
    except LookupError, NoResultFound:
        raise APIError(404, "not_found", "Candidate, product or decision not found.") from None
    except ValueError as exc:
        raise APIError(409, "decision_conflict", str(exc)) from None


@router.post("/decisions", response_model=Decision, status_code=201)
def create_match_decision(
    body: Annotated[Pair | Merge | Move, Body(discriminator="action")],
    session: DB,
    principal: CurrentPrincipal,
) -> Decision:
    """Accept, reject, merge, split or unlink, as the signed-in user. Skip is the client's own."""
    actor, reason = str(principal.user_id), body.reason or REASON
    product: UUID | None = None
    with refusals():
        if isinstance(body, Merge):
            product = decisions.merge(session, body.product_id, body.into, actor, reason)
        elif isinstance(body, Move) and body.action == "split":
            product = decisions.split(session, body.listing_ids, actor, reason, into=body.into)
        elif isinstance(body, Move):
            decisions.unlink(session, body.listing_ids, actor, reason)
        elif body.action == "accept":
            product = decisions.accept(session, body.candidate_id, actor, reason)
        else:
            decisions.reject(session, body.candidate_id, actor, reason)
    return decided(session, actor, body.action, product)


@router.post("/decisions/{decision_id}/undo", response_model=Decision, status_code=201)
def undo_match_decision(decision_id: int, session: DB, principal: CurrentPrincipal) -> Decision:
    """Reverse an owner decision with compensating rows; the history only grows (DEC-263 b)."""
    actor = str(principal.user_id)
    with refusals():
        decisions.undo(session, decision_id, actor, REASON)
    return decided(session, actor, "undo", None)
