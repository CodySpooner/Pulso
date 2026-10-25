"""Candidates from the HNSW image index, pending-only re-scoring and R-15 auto-links (DEC-249)."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, exists, func, or_, select, text, true
from sqlalchemy.orm import Session

from pulso_core.landed_cost import Amount, to_usd
from pulso_core.models import (
    FxRate,
    Image,
    Listing,
    ListingSnapshot,
    MatchCandidate,
    MatchDecision,
    Product,
)
from pulso_ml.matching.score import (
    CONFIG,
    Price,
    ScorerConfig,
    combined,
    price_sane,
    route,
    stored,
)
from pulso_ml.phash import similarity

# pulso_sources.fx_frankfurter.rate_as_of, passed in: pulso-sources already depends on pulso-ml.
RateLookup = Callable[[Session, str, date], FxRate | None]


@dataclass
class Counts:
    scored: int = 0
    linked: int = 0
    queued: int = 0
    discarded: int = 0
    skipped_no_embedding: int = 0


@dataclass
class Fact:
    listing: Listing
    phash: int | None
    price: Price | None


def canonical(merged: dict[UUID, UUID | None], product_id: UUID | None) -> UUID | None:
    """Follow merged_into_id to the live product; the visited set guards against a cycle."""
    visited = set()
    while product_id in merged and product_id not in visited:
        visited.add(product_id)
        product_id = merged[product_id]
    return product_id


def group(merged: dict[UUID, UUID | None], root: UUID) -> list[UUID]:
    """The live product and every product merged into it."""
    return [root, *(p for p in merged if canonical(merged, p) == root)]


def neighbours(
    listing: Listing, embedding: Any, same_product: Sequence[UUID], k: int
) -> Select[tuple[int, float]]:
    """Top-k listings by image cosine, on other stores and other canonical products."""
    distance = Image.embedding.cosine_distance(embedding)
    query = (
        select(Image.listing_id, 1 - distance)
        .join(Listing, Listing.id == Image.listing_id)
        .where(Image.embedding.is_not(None), Image.listing_id != listing.id)
        .order_by(distance)
        .limit(k)
    )
    if listing.store_id is not None:
        query = query.where(Listing.store_id.is_distinct_from(listing.store_id))
    if same_product:
        query = query.where(
            or_(Listing.product_id.is_(None), Listing.product_id.not_in(same_product))
        )
    return query


def match(session: Session, rates: RateLookup, config: ScorerConfig = CONFIG) -> Counts:
    """Score each embedded listing's neighbours; one transaction per listing.

    ponytail: a full pass every run (one HNSW query per listing); restrict to listings
    with new images or titles once the universe makes a pass slow.
    """
    embedded = exists().where(Image.listing_id == Listing.id, Image.embedding.is_not(None))
    counts = Counts(
        skipped_no_embedding=session.scalar(
            select(func.count()).select_from(Listing).where(~embedded)
        )
        or 0
    )
    merged = dict(
        session.execute(
            select(Product.id, Product.merged_into_id).where(Product.merged_into_id.is_not(None))
        )
        .tuples()
        .all()
    )
    usd_rates: dict[tuple[str, date], Decimal | None] = {}
    seen: set[tuple[int, int]] = set()

    def price(listing: Listing, minor: int | None, currency: str, day: date) -> Price | None:
        if minor is None:
            return None
        if currency != "USD" and (currency, day) not in usd_rates:
            row = rates(session, currency, day)
            usd_rates[currency, day] = None if row is None else row.rate
        usd = to_usd(Amount(minor, currency, usd_rates.get((currency, day))))
        return None if usd is None else Price(usd, supplier=listing.supplier_id is not None)

    for listing_id in session.scalars(
        select(Listing.id).where(embedded).order_by(Listing.id)
    ).all():
        # Filters past the first ef_search hits keep scanning the index (pgvector 0.8).
        session.execute(text("SET LOCAL hnsw.iterative_scan = strict_order"))
        source = session.get_one(Listing, listing_id)
        embedding = session.scalar(
            select(Image.embedding)
            .where(Image.listing_id == listing_id, Image.embedding.is_not(None))
            .order_by(Image.position, Image.id)
            .limit(1)
        )
        root = canonical(merged, source.product_id)
        same_product = [] if root is None else group(merged, root)
        hits: dict[int, float] = {}
        for other_id, cos in session.execute(
            neighbours(source, embedding, same_product, config.top_k)
        ).tuples():
            hits[other_id] = max(cos, hits.get(other_id, cos))  # one row per embedded image
        titles: dict[int, float | None] = {}
        if source.title_embedding is not None:
            distance = Listing.title_embedding.cosine_distance(source.title_embedding)
            titles.update(
                session.execute(select(Listing.id, 1 - distance).where(Listing.id.in_(hits)))
                .tuples()
                .all()
            )
        facts = load_facts(session, [listing_id, *hits], price)
        for other_id, image_cos in hits.items():
            pair = (min(listing_id, other_id), max(listing_id, other_id))
            if pair in seen:
                continue
            seen.add(pair)
            a, b = facts[pair[0]], facts[pair[1]]
            products = {canonical(merged, fact.listing.product_id) for fact in (a, b)}
            if len(products) == 1 and None not in products:
                continue  # linked earlier in this run
            candidate = session.scalar(
                select(MatchCandidate)
                .where(
                    MatchCandidate.listing_a_id == pair[0], MatchCandidate.listing_b_id == pair[1]
                )
                .with_for_update()
            )
            if candidate is not None and candidate.status != "pending":
                continue  # accepted, rejected, merged and split pairs are never touched
            phash_sim = None if a.phash is None or b.phash is None else similarity(a.phash, b.phash)
            score = combined(config, image_cos, titles.get(other_id), phash_sim)
            assert score is not None  # image_cos is always present
            sane = price_sane(config, a.price, b.price)
            verdict = route(config, score, sane)
            counts.scored += 1
            values = {
                "image_cos": stored(image_cos),
                "title_cos": stored(titles.get(other_id)),
                "phash_sim": stored(phash_sim),
                "price_sane": sane,
                "score": score,
                "scorer_version": config.version,
            }
            if candidate is None:
                if verdict == "discard":
                    counts.discarded += 1
                    continue
                candidate = MatchCandidate(
                    listing_a_id=pair[0], listing_b_id=pair[1], status="pending", **values
                )
                session.add(candidate)
                session.flush()
            else:
                for key, value in values.items():  # the ORM writes only changed values
                    setattr(candidate, key, value)
            if verdict == "link" and link(session, candidate, merged, config):
                counts.linked += 1
            elif verdict == "discard":
                counts.discarded += 1
            else:
                counts.queued += 1
        session.commit()
    return counts


def load_facts(
    session: Session,
    ids: list[int],
    price: Callable[[Listing, int | None, str, date], Price | None],
) -> dict[int, Fact]:
    main_phash = (
        select(Image.phash)
        .where(Image.listing_id == Listing.id, Image.phash.is_not(None))
        .order_by(Image.position, Image.id)
        .limit(1)
        .scalar_subquery()
    )
    latest = (
        select(
            ListingSnapshot.price_min_minor, ListingSnapshot.currency, ListingSnapshot.observed_for
        )
        .where(ListingSnapshot.listing_id == Listing.id)
        .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
        .limit(1)
        .lateral()
    )
    rows = session.execute(
        select(
            Listing, main_phash, latest.c.price_min_minor, latest.c.currency, latest.c.observed_for
        )
        .outerjoin(latest, true())
        .where(Listing.id.in_(ids))
    ).tuples()
    return {
        listing.id: Fact(
            listing, phash, None if currency is None else price(listing, minor, currency, day)
        )
        for listing, phash, minor, currency, day in rows
    }


def link(
    session: Session,
    candidate: MatchCandidate,
    merged: dict[UUID, UUID | None],
    config: ScorerConfig,
) -> bool:
    """Point the pair's product-less listings at one product, one decision per pointer (R-15).

    Listings already on a product never move: two products is a merge, left pending for
    the queue (M-5). Nor does a listing whose latest decision is manual, nor one that would
    join a listing it has a rejected or split pair with. Two product-less listings form a
    new product named after the older one.
    """
    pair = session.scalars(
        select(Listing)
        .where(Listing.id.in_((candidate.listing_a_id, candidate.listing_b_id)))
        .order_by(Listing.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    movers = [listing for listing in pair if listing.product_id is None]
    if not movers or any(manual(session, listing.id) for listing in movers):
        return False
    if len(movers) == 1:
        target = canonical(
            merged, next(lst.product_id for lst in pair if lst.product_id is not None)
        )
        if target is None or vetoed(session, movers[0].id, group(merged, target)):
            return False
    else:
        older = min(pair, key=lambda listing: (listing.first_seen_at, listing.id))
        product = Product(name=older.title, first_seen_at=older.first_seen_at)
        session.add(product)
        session.flush()
        target = product.id
    for listing in movers:
        session.add(
            MatchDecision(
                actor="algo",
                action="link",
                listing_id=listing.id,
                from_product_id=None,
                to_product_id=target,
                candidate_id=candidate.id,
                confidence=candidate.score,
                reason=f"{config.version}: score {candidate.score} >= auto {config.auto}",
            )
        )
        listing.product_id, listing.match_confidence = target, candidate.score
    candidate.status, candidate.decided_at = "accepted", func.now()
    return True


def vetoed(session: Session, listing_id: int, product_ids: list[UUID]) -> bool:
    """A rejected or split pair would end up on one product through a third listing."""
    a, b = MatchCandidate.listing_a_id, MatchCandidate.listing_b_id
    return bool(
        session.scalar(
            select(
                exists().where(
                    MatchCandidate.status.in_(("rejected", "split")),
                    or_(a == listing_id, b == listing_id),
                    Listing.id == case((a == listing_id, b), else_=a),
                    Listing.product_id.in_(product_ids),
                )
            )
        )
    )


def manual(session: Session, listing_id: int) -> bool:
    """The listing's latest decision is by an owner or user: the matcher never moves it."""
    actor = session.scalar(
        select(MatchDecision.actor)
        .where(MatchDecision.listing_id == listing_id)
        .order_by(MatchDecision.decided_at.desc(), MatchDecision.id.desc())
        .limit(1)
    )
    return actor not in (None, "algo")
