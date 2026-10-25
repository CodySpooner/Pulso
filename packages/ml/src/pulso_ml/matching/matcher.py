"""GTIN pairs (DEC-255), then HNSW candidates, pending-only re-scoring and auto-links (DEC-249)."""

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import combinations
from typing import Any
from uuid import UUID

from sqlalchemy import Select, case, exists, func, or_, select, text, true, update
from sqlalchemy.orm import Session, aliased

from pulso_core.landed_cost import Amount, to_usd
from pulso_core.models import (
    FxRate,
    Image,
    Listing,
    ListingSnapshot,
    ListingVariant,
    MatchCandidate,
    MatchDecision,
    Product,
)
from pulso_ml.matching.gtin import gtin14
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
# match_candidates.scorer_version of a GTIN pair; bump it when gtin14's rules change.
GTIN_VERSION = "gtin-1"
# pg_advisory_xact_lock key ("PULSMATC"); bigint keys never meet the workers' two-int locks.
MATCHING_LOCK = 0x50554C534D415443


@dataclass
class Counts:
    scored: int = 0
    linked: int = 0
    queued: int = 0
    discarded: int = 0
    skipped_no_embedding: int = 0
    gtin_linked: int = 0
    gtin_queued: int = 0


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


def redirects(session: Session) -> dict[UUID, UUID | None]:
    return dict(
        session.execute(
            select(Product.id, Product.merged_into_id).where(Product.merged_into_id.is_not(None))
        )
        .tuples()
        .all()
    )


def lock(session: Session) -> None:
    """Every matching write holds one transaction lock, so a run and a decision never interleave.

    A merge moves every listing of the merged product under it, so no pointer read after
    the lock names a product merged since the run loaded its redirects.
    ponytail: one global lock; per-product locks if decisions ever queue behind a run.
    """
    session.execute(select(func.pg_advisory_xact_lock(MATCHING_LOCK)))


def new_product(session: Session, listings: Sequence[Listing]) -> UUID:
    """A product named after the older listing (first_seen_at, then id), seen when it was."""
    older = min(listings, key=lambda listing: (listing.first_seen_at, listing.id))
    product = Product(name=older.title, first_seen_at=older.first_seen_at)
    session.add(product)
    session.flush()
    return product.id


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
    """Link GTIN pairs, then score each embedded listing's neighbours; one transaction per listing.

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
    merged = redirects(session)
    gtins(session, merged, counts)
    usd_rates: dict[tuple[str, date], Decimal | None] = {}
    seen: set[tuple[int, int]] = set()

    def price(listing: Listing, minor: int | None, currency: str, day: date) -> Price | None:
        if minor is None:
            return None
        if currency != "USD" and (currency, day) not in usd_rates:
            row = rates(session, currency, day)
            usd_rates[currency, day] = None if row is None else row.rate
        try:
            usd = to_usd(Amount(minor, currency, usd_rates.get((currency, day))))
        except ValueError:  # past BIGINT in USD: no price, as in cheapest() (XR-26)
            usd = None
        return None if usd is None else Price(usd, supplier=listing.supplier_id is not None)

    for listing_id in session.scalars(
        select(Listing.id).where(embedded).order_by(Listing.id)
    ).all():
        lock(session)
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
        # The top k listings, not image rows: ask again for 4x the rows while one listing's
        # images crowd the k nearest (XR-24). ponytail: the scan stops at hnsw.max_scan_tuples.
        limit = config.top_k
        while True:
            query = neighbours(source, embedding, same_product, limit)
            rows = session.execute(query).tuples().all()
            hits: dict[int, float] = {}
            for other_id, cos in rows:
                hits[other_id] = max(cos, hits.get(other_id, cos))  # one row per embedded image
            if len(hits) >= config.top_k or len(rows) < limit:
                break
            limit *= 4
        hits = dict(list(hits.items())[: config.top_k])  # rows come nearest first
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
            if apart(session, merged, a.listing, b.listing):
                continue
            candidate = session.scalar(
                select(MatchCandidate)
                .where(
                    MatchCandidate.listing_a_id == pair[0], MatchCandidate.listing_b_id == pair[1]
                )
                .with_for_update()
            )
            if candidate is not None and (
                candidate.status != "pending" or candidate.scorer_version == GTIN_VERSION
            ):
                continue  # decided pairs are never touched; a GTIN pair outranks any score
            phash_sim = None if a.phash is None or b.phash is None else similarity(a.phash, b.phash)
            score = combined(config, image_cos, titles.get(other_id), phash_sim)
            if score is None:  # no component left: a NaN image cosine is missing too (XR-26)
                continue
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
            reason = f"{config.version}: score {score} >= auto {config.auto}"
            if verdict == "link" and link(session, candidate, merged, reason):
                counts.linked += 1
            elif verdict == "discard":  # below the band now: out of the queue (DEC-260 c)
                candidate.status, candidate.decided_at = "rejected", func.now()
                counts.discarded += 1
            else:
                counts.queued += 1
        session.commit()
    settle(session)
    return counts


def settle(session: Session) -> None:
    """Pending pairs whose listings are already on one product are accepted (DEC-260 d).

    Nothing moves, so no decision row (R-15). Same-product listings are never neighbours,
    so without this a pair queued before both joined one product would stay queued.
    """
    lock(session)
    merged = redirects(session)
    a, b = aliased(Listing), aliased(Listing)
    rows = session.execute(
        select(MatchCandidate.id, a.product_id, b.product_id)
        .join(a, a.id == MatchCandidate.listing_a_id)
        .join(b, b.id == MatchCandidate.listing_b_id)
        .where(
            MatchCandidate.status == "pending", a.product_id.is_not(None), b.product_id.is_not(None)
        )
    ).tuples()
    ids = [id_ for id_, x, y in rows if canonical(merged, x) == canonical(merged, y)]
    if ids:
        session.execute(
            update(MatchCandidate)
            .where(MatchCandidate.id.in_(ids))
            .values(status="accepted", decided_at=func.now())
        )
    session.commit()


def gtins(session: Session, merged: dict[UUID, UUID | None], counts: Counts) -> None:
    """Listings of different vendors sharing a valid GTIN pair at score 1.0 (M-4, DEC-255).

    A vendor that puts one GTIN on two of its listings isn't using it as an identifier, so
    those listings drop out of that GTIN. Each pair goes through link(), so M-3's R-15,
    two-product and manual rules hold. One transaction per GTIN.

    ponytail: every barcode is read into memory each run; group a normalised column in SQL
    once listing_variants outgrows that.
    """
    groups: defaultdict[str, defaultdict[tuple[int | None, ...], set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for barcode, listing_id, store_id, supplier_id in session.execute(
        select(ListingVariant.barcode, Listing.id, Listing.store_id, Listing.supplier_id)
        .join(Listing, Listing.id == ListingVariant.listing_id)
        .where(ListingVariant.barcode.is_not(None))
    ).tuples():
        if (code := gtin14(barcode)) is not None:
            vendorless = store_id is None and supplier_id is None
            groups[code][store_id, supplier_id, listing_id if vendorless else None].add(listing_id)
    seen: set[tuple[int, int]] = set()
    for code, vendors in sorted(groups.items()):
        ids = sorted(next(iter(listings)) for listings in vendors.values() if len(listings) == 1)
        for pair in combinations(ids, 2):
            if pair in seen:
                continue
            seen.add(pair)
            lock(session)  # held until this GTIN's commit; taking it again is a no-op
            a, b = session.scalars(select(Listing).where(Listing.id.in_(pair))).all()
            products = {canonical(merged, listing.product_id) for listing in (a, b)}
            if len(products) == 1 and None not in products:
                continue  # already on one product
            if apart(session, merged, a, b):
                continue
            candidate = session.scalar(
                select(MatchCandidate)
                .where(
                    MatchCandidate.listing_a_id == pair[0], MatchCandidate.listing_b_id == pair[1]
                )
                .with_for_update()
            )
            if candidate is not None and candidate.status != "pending":
                continue  # accepted, rejected, merged and split pairs are never touched
            if candidate is None:
                candidate = MatchCandidate(
                    listing_a_id=pair[0],
                    listing_b_id=pair[1],
                    status="pending",
                    score=Decimal(1),
                    scorer_version=GTIN_VERSION,
                )
                session.add(candidate)
                session.flush()
            else:  # a GTIN outranks an image/title score; the components stay as evidence
                candidate.score, candidate.scorer_version = Decimal(1), GTIN_VERSION
            if link(session, candidate, merged, f"{GTIN_VERSION}: GTIN {code}"):
                counts.gtin_linked += 1
            else:
                counts.gtin_queued += 1
        session.commit()


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
    reason: str,
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
        target = new_product(session, pair)
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
                reason=reason,
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


def apart(session: Session, merged: dict[UUID, UUID | None], a: Listing, b: Listing) -> bool:
    """The owner split one listing off the other's product: never paired again (DEC-257 b)."""
    off = [
        (listing.id, group(merged, root))
        for listing, other in ((a, b), (b, a))
        if (root := canonical(merged, other.product_id)) is not None
    ]
    return bool(off) and bool(
        session.scalar(
            select(
                exists().where(
                    MatchDecision.action == "split",
                    or_(
                        *(
                            (MatchDecision.listing_id == listing_id)
                            & MatchDecision.from_product_id.in_(product_ids)
                            for listing_id, product_ids in off
                        )
                    ),
                )
            )
        )
    )


def manual(session: Session, listing_id: int) -> bool:
    """The listing's latest move is by an owner or user: the matcher never moves it.

    A reject moves nothing: it holds only its pair, through the candidate's status. Latest
    is the highest id, the order moves took the lock (XR-29, DEC-266).
    """
    actor = session.scalar(
        select(MatchDecision.actor)
        .where(MatchDecision.listing_id == listing_id, MatchDecision.action != "reject")
        .order_by(MatchDecision.id.desc())
        .limit(1)
    )
    return actor not in (None, "algo")
