"""Owner decisions: merge, split, accept and reject, and membership(t) replay (M-5, DEC-257).

Every listings.product_id change appends one match_decisions row (R-15). Each call takes
the matcher's transaction lock first and leaves the commit to the caller.
"""

from collections.abc import Collection, Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from pulso_core.models import Listing, MatchCandidate, MatchDecision, Product
from pulso_ml.matching.matcher import canonical, group, lock, new_product, redirects


def merge(
    session: Session,
    product_id: UUID,
    into: UUID,
    actor: str,
    reason: str,
    *,
    candidate: MatchCandidate | None = None,
) -> UUID:
    """Merge a product into another and return the survivor. Both ids follow merged_into_id.

    Every listing on the merged product, or on one merged into it earlier, moves with one
    decision each. Pending pairs the move puts on one product are settled as merged.
    """
    lock(session)
    merged = redirects(session)
    source, target = canonical(merged, product_id), canonical(merged, into)
    assert source is not None and target is not None
    if source == target:
        raise ValueError(f"products {product_id} and {into} are already one product")
    product = session.get_one(Product, source)
    product.merged_into_id, product.status = target, "merged"
    moved = session.scalars(
        select(Listing).where(Listing.product_id.in_(group(merged, source))).order_by(Listing.id)
    ).all()
    for listing in moved:
        record(session, listing, target, actor, "merge", reason, candidate)
    ids = [listing.id for listing in moved]
    on_target = select(Listing.id).where(Listing.product_id == target)
    session.execute(
        update(MatchCandidate)
        .where(
            MatchCandidate.status == "pending",
            or_(MatchCandidate.listing_a_id.in_(ids), MatchCandidate.listing_b_id.in_(ids)),
            MatchCandidate.listing_a_id.in_(on_target),
            MatchCandidate.listing_b_id.in_(on_target),
        )
        .values(status="merged", decided_at=func.now())
    )
    return target


def split(
    session: Session,
    listing_ids: Collection[int],
    actor: str,
    reason: str,
    *,
    into: UUID | None = None,
) -> UUID:
    """Move listings of one product onto `into`, or a new product, and return where they went.

    One listing at least stays behind: moving a whole product is a merge. Candidate pairs
    between moved and staying listings are marked split. The matcher reads the split
    decisions themselves, so it never pairs a moved listing with that product again.
    """
    lock(session)
    merged = redirects(session)
    listings = session.scalars(
        select(Listing).where(Listing.id.in_(listing_ids)).order_by(Listing.id)
    ).all()
    sources = {canonical(merged, listing.product_id) for listing in listings}
    if len(listings) != len(set(listing_ids)) or len(sources) != 1 or None in sources:
        raise ValueError("a split takes existing listings of one product")
    (source,) = sources
    assert source is not None
    stay = session.scalars(
        select(Listing.id).where(
            Listing.product_id.in_(group(merged, source)), Listing.id.not_in(listing_ids)
        )
    ).all()
    if not stay:
        raise ValueError("a split leaves one listing at least; merge moves a whole product")
    target = new_product(session, listings) if into is None else canonical(merged, into)
    assert target is not None
    if target == source:
        raise ValueError(f"listings already on product {into}")
    for listing in listings:
        record(session, listing, target, actor, "split", reason, None)
    a, b, ids = MatchCandidate.listing_a_id, MatchCandidate.listing_b_id, list(listing_ids)
    session.execute(
        update(MatchCandidate)
        .where(
            MatchCandidate.status.not_in(("rejected", "split")),
            or_(and_(a.in_(ids), b.in_(stay)), and_(a.in_(stay), b.in_(ids))),
        )
        .values(status="split", decided_at=func.now())
    )
    return target


def accept(session: Session, candidate_id: int, actor: str, reason: str) -> UUID:
    """Put a pending pair on one product and return it.

    Two products merge, the younger (first_seen_at, then id) into the older. A product-less
    listing joins the other's product; two form a new product named after the older one.
    """
    lock(session)
    candidate = pending(session, candidate_id)
    merged = redirects(session)
    pair = pair_of(session, candidate)
    roots = {canonical(merged, listing.product_id) for listing in pair} - {None}
    candidate.decided_at = func.now()
    if len(roots) == 2:
        older, younger = sorted(
            (session.get_one(Product, root) for root in roots),
            key=lambda product: (product.first_seen_at, product.id),
        )
        candidate.status = "merged"
        return merge(session, younger.id, older.id, actor, reason, candidate=candidate)
    target = roots.pop() if roots else new_product(session, pair)
    assert target is not None
    for listing in pair:
        if listing.product_id is None:
            record(session, listing, target, actor, "accept", reason, candidate)
    candidate.status = "accepted"
    return target


def reject(session: Session, candidate_id: int, actor: str, reason: str) -> None:
    """Keep a pending pair apart: one decision per listing, both pointers unchanged.

    The matcher never links the pair, nor through a third listing (DEC-249 h), but each
    listing can still link elsewhere.
    """
    lock(session)
    candidate = pending(session, candidate_id)
    for listing in pair_of(session, candidate):
        record(session, listing, listing.product_id, actor, "reject", reason, candidate)
    candidate.status, candidate.decided_at = "rejected", func.now()


def membership(session: Session, at: datetime) -> dict[int, UUID]:
    """Each listing's product as of `at`: the latest decision before it (R-15).

    Replays match_decisions alone, never listings.product_id or merged_into_id, which hold
    today's state, so a later merge or split can't change an earlier answer. A listing with
    no decision before `at`, or none that put it on a product, is absent. The latest is the
    highest id: every writer inserts under the matching lock, so ids follow the order moves
    took it, while decided_at is each transaction's start (XR-29, DEC-266).
    ponytail: one pass over the log per call; materialise membership if replay measures slow.
    """
    rows = session.execute(
        select(MatchDecision.listing_id, MatchDecision.to_product_id)
        .where(MatchDecision.decided_at < at)
        .order_by(MatchDecision.listing_id, MatchDecision.id.desc())
        .distinct(MatchDecision.listing_id)
    ).tuples()
    return {listing_id: product_id for listing_id, product_id in rows if product_id is not None}


def pending(session: Session, candidate_id: int) -> MatchCandidate:
    candidate = session.get_one(MatchCandidate, candidate_id)
    if candidate.status != "pending":
        raise ValueError(f"candidate {candidate_id} is {candidate.status}, not pending")
    return candidate


def pair_of(session: Session, candidate: MatchCandidate) -> Sequence[Listing]:
    return session.scalars(
        select(Listing)
        .where(Listing.id.in_((candidate.listing_a_id, candidate.listing_b_id)))
        .order_by(Listing.id)
    ).all()


def record(
    session: Session,
    listing: Listing,
    to: UUID | None,
    actor: str,
    action: str,
    reason: str,
    candidate: MatchCandidate | None,
) -> None:
    """One decision row; a moved listing loses match_confidence, which is the matcher's score."""
    session.add(
        MatchDecision(
            actor=actor,
            action=action,
            listing_id=listing.id,
            from_product_id=listing.product_id,
            to_product_id=to,
            candidate_id=None if candidate is None else candidate.id,
            reason=reason,
        )
    )
    if to != listing.product_id:
        listing.product_id, listing.match_confidence = to, None
