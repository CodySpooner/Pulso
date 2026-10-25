import math
from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    FxRate,
    Image,
    Listing,
    ListingSnapshot,
    ListingVariant,
    MatchCandidate,
    MatchDecision,
    Product,
    RawPayload,
    Store,
    Supplier,
)
from pulso_core.models.catalog import EMBEDDING_DIM
from pulso_ml.matching.matcher import GTIN_VERSION, Counts, match, neighbours
from pulso_ml.matching.score import CONFIG

pytestmark = pytest.mark.db

DAY = date(2026, 10, 24)
SEEN = datetime(2026, 10, 1, tzinfo=UTC)


def direction(axis: int, degrees: float = 0.0) -> list[float]:
    """A unit vector in plane `axis`; two in one plane have cosine cos(angle between them)."""
    vector = [0.0] * EMBEDDING_DIM
    vector[2 * axis] = math.cos(math.radians(degrees))
    vector[2 * axis + 1] = math.sin(math.radians(degrees))
    return vector


QUEUE_ANGLE = math.degrees(math.acos(0.8))  # 0.85 * 0.8 + 0.15 = 0.83: the queue band


class World:
    def __init__(self, session: Session) -> None:
        self.session = session
        run = CollectorRun(source_id=1, trigger="manual", status="success")
        session.add(run)
        session.flush()
        self.payload = RawPayload(source_id=1, run_id=run.id, request={}, bytes=1, sha256="0" * 64)
        session.add(self.payload)
        session.flush()
        self.n = 0
        self.rate_calls: list[tuple[str, date]] = []

    def store(self) -> Store:
        store = Store(domain=f"s{uuid4().hex[:8]}.example", platform="shopify")
        self.session.add(store)
        self.session.flush()
        return store

    def supplier(self) -> Supplier:
        supplier = Supplier(platform="cj", external_id=uuid4().hex, name="Supplier")
        self.session.add(supplier)
        self.session.flush()
        return supplier

    def product(self, merged_into: UUID | None = None) -> UUID:
        product = Product(name="Existing", merged_into_id=merged_into)
        self.session.add(product)
        self.session.flush()
        return product.id

    def listing(
        self,
        vendor: Store | Supplier,
        axis: int,
        degrees: float = 0.0,
        *,
        price: int | None = 1000,
        currency: str = "USD",
        product: UUID | None = None,
        embedded: bool = True,
        age_days: int = 0,
    ) -> Listing:
        self.n += 1
        vector = direction(axis, degrees)
        listing = Listing(
            source_id=1,
            external_id=f"x{self.n}",
            url=f"https://example.test/{self.n}",
            title=f"Lamp {self.n}",
            title_embedding=vector,
            product_id=product,
            store_id=vendor.id if isinstance(vendor, Store) else None,
            supplier_id=vendor.id if isinstance(vendor, Supplier) else None,
            first_seen_at=SEEN - timedelta(days=age_days),
        )
        self.session.add(listing)
        self.session.flush()
        self.session.add(
            Image(
                listing_id=listing.id,
                url=f"https://example.test/{self.n}.jpg",
                position=1,
                phash=-12345,
                embedding=vector if embedded else None,
            )
        )
        if price is not None:
            self.session.add(
                ListingSnapshot(
                    listing_id=listing.id,
                    observed_for=DAY,
                    raw_payload_id=self.payload.id,
                    values_hash=uuid4().hex,
                    price_min_minor=price,
                    currency=currency,
                )
            )
        self.session.flush()
        return listing

    def barcode(self, listing: Listing, barcode: str) -> None:
        self.session.add(
            ListingVariant(listing_id=listing.id, external_id=uuid4().hex, barcode=barcode)
        )
        self.session.flush()

    def rates(self, session: Session, quote: str, day: date) -> FxRate | None:
        self.rate_calls.append((quote, day))
        return FxRate(rate=Decimal("150")) if quote == "JPY" else None

    def run(self) -> Counts:
        self.session.commit()
        return match(self.session, self.rates)


@pytest.fixture
def world(db_engine: Engine) -> Iterator[World]:
    with Session(db_engine) as session:
        yield World(session)


def products(session: Session, *listings: Listing) -> list[UUID | None]:
    for listing in listings:
        session.refresh(listing)
    return [listing.product_id for listing in listings]


def candidate(session: Session, a: Listing, b: Listing) -> MatchCandidate | None:
    low, high = sorted((a.id, b.id))
    return session.scalar(
        select(MatchCandidate)
        .where(MatchCandidate.listing_a_id == low, MatchCandidate.listing_b_id == high)
        .execution_options(populate_existing=True)
    )


def table(session: Session, model: Any) -> list[tuple[Any, ...]]:
    session.expire_all()
    rows = session.execute(select(model.__table__).order_by(model.__table__.c.id)).all()
    return [tuple(row) for row in rows]


def test_neighbours_use_hnsw_and_exclude_same_store_and_same_product(world: World) -> None:
    store, other_store = world.store(), world.store()
    product = world.product()
    merged_in = world.product(merged_into=product)
    source = world.listing(store, 0, product=product)
    same_store = world.listing(store, 0, 1)
    same_product = world.listing(other_store, 0, 2, product=product)
    merged_product = world.listing(other_store, 0, 3, product=merged_in)
    kept = world.listing(other_store, 0, 4)
    supplier_listing = world.listing(world.supplier(), 0, 5)
    session = world.session
    query = neighbours(source, direction(0), [product, merged_in], CONFIG.top_k)
    hits = [listing_id for listing_id, _ in session.execute(query)]
    assert hits == [kept.id, supplier_listing.id]
    assert not {same_store.id, same_product.id, merged_product.id} & set(hits)

    session.execute(text("SET LOCAL enable_seqscan = off"))
    sql = str(query.compile(session.connection(), compile_kwargs={"literal_binds": True}))
    plan = "\n".join(session.connection().exec_driver_sql("EXPLAIN " + sql).scalars())
    assert "Index Scan using ix_images_embedding" in plan


def test_auto_link_forms_a_product_and_logs_one_decision_per_pointer(world: World) -> None:
    cost = world.listing(world.supplier(), 0, price=1000, age_days=9)  # $10.00 supplier cost
    retail = world.listing(world.store(), 0, price=2500)  # $25.00
    retail_jpy = world.listing(world.store(), 0, price=4500, currency="JPY")  # $30.00
    counts = world.run()
    session = world.session

    first, second, third = products(session, cost, retail, retail_jpy)
    assert first is not None and first == second == third
    product = session.get_one(Product, first)
    assert (product.name, product.first_seen_at) == (cost.title, cost.first_seen_at)
    assert ("JPY", DAY) in world.rate_calls  # FX on the snapshot's day
    decisions = session.scalars(select(MatchDecision).order_by(MatchDecision.id)).all()
    assert sorted(d.listing_id for d in decisions) == [cost.id, retail.id, retail_jpy.id]
    for decision in decisions:
        assert (decision.actor, decision.action) == ("algo", "link")
        assert (decision.from_product_id, decision.to_product_id) == (None, first)
        assert decision.confidence == Decimal("1.0000")
        assert decision.reason is not None and CONFIG.version in decision.reason
        linked = session.get_one(MatchCandidate, decision.candidate_id)
        assert (linked.status, linked.scorer_version, linked.price_sane) == (
            "accepted",
            CONFIG.version,
            True,
        )
        assert linked.decided_at is not None
    assert session.get_one(Listing, retail.id).match_confidence == Decimal("1.0000")
    assert counts.linked == 2  # the pair forms the product, then the JPY listing joins it


def test_insane_or_unknown_price_queues_and_two_products_stay_pending(world: World) -> None:
    insane = (world.listing(world.supplier(), 0, price=100), world.listing(world.store(), 0))
    unknown = (world.listing(world.store(), 1, price=None), world.listing(world.store(), 1))
    two_products = (
        world.listing(world.store(), 2, product=world.product()),
        world.listing(world.store(), 2, product=world.product()),
    )
    before = [products(world.session, *pair) for pair in (insane, unknown, two_products)]
    world.run()
    session = world.session
    for pair, was in zip((insane, unknown, two_products), before, strict=True):
        row = candidate(session, *pair)
        assert row is not None and (row.status, row.score) == ("pending", Decimal("1.0000"))
        assert products(session, *pair) == was
    assert [candidate(session, *pair).price_sane for pair in (insane, unknown)] == [False, None]  # type: ignore[union-attr]
    assert session.scalar(select(func.count()).select_from(MatchDecision)) == 0


def test_pending_rows_rescore_and_decided_rows_never_change(world: World) -> None:
    queued = (world.listing(world.store(), 0), world.listing(world.store(), 0, QUEUE_ANGLE))
    rejected = (world.listing(world.store(), 1), world.listing(world.store(), 1))
    bridge = world.listing(world.store(), 1)  # matches both sides of the rejected pair
    low_store = world.listing(world.store(), 2)
    discarded = world.listing(world.store(), 2, 60)  # cosine 0.5: below the queue band
    unembedded = world.listing(world.store(), 3, embedded=False)
    session = world.session
    for (a, b), status in ((queued, "pending"), (rejected, "rejected")):
        low, high = sorted((a.id, b.id))
        session.add(
            MatchCandidate(
                listing_a_id=low,
                listing_b_id=high,
                score=Decimal("0.5"),
                scorer_version="m3-older",
                status=status,
            )
        )
    world.session.flush()
    rejected_before = table(session, MatchCandidate)[1]
    counts = world.run()

    pending = candidate(session, *queued)
    assert pending is not None
    assert (pending.status, pending.score, pending.scorer_version) == (
        "pending",
        Decimal("0.8300"),
        CONFIG.version,
    )
    assert table(session, MatchCandidate)[1] == rejected_before
    # The first side and the bridge form a product; the other side never joins it.
    first, other, bridged = products(session, *rejected, bridge)
    assert first is not None and first == bridged and other is None
    assert candidate(session, rejected[1], bridge).status == "pending"  # type: ignore[union-attr]
    assert candidate(session, low_store, discarded) is None
    assert products(session, unembedded) == [None]
    assert counts.skipped_no_embedding == 1


def test_manual_decisions_are_never_undone(world: World) -> None:
    session = world.session
    curated, elsewhere = world.product(), world.product()
    unlinked = world.listing(world.store(), 0)
    target = world.listing(world.store(), 0, product=curated)
    kept = world.listing(world.store(), 1, product=elsewhere)
    world.listing(world.store(), 1, product=curated)
    session.add_all(
        [
            MatchDecision(
                actor="owner",
                action="unlink",
                listing_id=unlinked.id,
                from_product_id=curated,
                reason="manual",
            ),
            MatchDecision(
                actor="owner", action="link", listing_id=kept.id, to_product_id=elsewhere
            ),
        ]
    )
    session.flush()
    manual_rows = table(session, MatchDecision)
    world.run()
    world.run()  # a re-run doesn't undo them either
    assert products(session, unlinked, kept) == [None, elsewhere]
    assert table(session, MatchDecision) == manual_rows
    assert candidate(session, unlinked, target).status == "pending"  # type: ignore[union-attr]


def test_r15_every_pointer_change_has_exactly_one_decision_and_reruns_add_nothing(
    world: World,
) -> None:
    session = world.session
    existing = world.product()
    for axis in range(6):
        world.listing(world.supplier(), axis, price=1000, age_days=axis)
        world.listing(world.store(), axis, price=2000 + axis)
        world.listing(world.store(), axis, QUEUE_ANGLE, price=3000)
    world.listing(world.store(), 6, product=existing)
    world.listing(world.store(), 6, 1)  # joins the existing product
    world.listing(world.store(), 7, embedded=False)
    session.commit()
    before = dict(session.execute(select(Listing.id, Listing.product_id)).tuples().all())

    first = world.run()
    after = dict(session.execute(select(Listing.id, Listing.product_id)).tuples().all())
    decisions = session.execute(
        select(MatchDecision.listing_id, MatchDecision.from_product_id, MatchDecision.to_product_id)
    ).all()
    per_listing = Counter(listing_id for listing_id, _, _ in decisions)
    changed = {listing_id for listing_id, old in before.items() if after[listing_id] != old}
    # Per plane the supplier and the $20 listing form a product; the 0.83 listing queues.
    assert len(changed) == 6 * 2 + 1 and first.linked == 6 + 1
    for listing_id in before:
        assert per_listing[listing_id] == (listing_id in changed)
    for listing_id, old, new in decisions:
        assert (old, new) == (before[listing_id], after[listing_id])
    assert first.skipped_no_embedding == 1
    assert first.scored == first.linked + first.queued + first.discarded

    candidates, all_decisions = table(session, MatchCandidate), table(session, MatchDecision)
    second = world.run()
    assert second.linked == 0
    assert table(session, MatchCandidate) == candidates
    assert table(session, MatchDecision) == all_decisions
    assert dict(session.execute(select(Listing.id, Listing.product_id)).tuples().all()) == after


def test_shared_gtin_links_across_formats_at_confidence_one_and_reruns_add_nothing(
    world: World,
) -> None:
    # No embeddings, and a price M-3's gate calls insane: only the GTIN pass can link them.
    upc = world.listing(world.store(), 0, embedded=False, age_days=1)
    ean = world.listing(world.supplier(), 1, price=5000, embedded=False)
    world.barcode(upc, "036000291452")
    world.barcode(ean, "0036000291452")
    world.barcode(ean, "not a barcode")
    counts = world.run()
    session = world.session

    first, second = products(session, upc, ean)
    assert first is not None and first == second
    assert session.get_one(Product, first).name == upc.title  # named after the older listing
    pair = candidate(session, upc, ean)
    assert pair is not None
    assert (pair.status, pair.score, pair.scorer_version) == (
        "accepted",
        Decimal("1.0000"),
        GTIN_VERSION,
    )
    decisions = session.scalars(select(MatchDecision).order_by(MatchDecision.listing_id)).all()
    assert [decision.listing_id for decision in decisions] == sorted((upc.id, ean.id))
    for decision in decisions:
        assert (decision.actor, decision.action, decision.candidate_id) == ("algo", "link", pair.id)
        assert (decision.from_product_id, decision.to_product_id) == (None, first)
        assert decision.confidence == Decimal("1.0000")
        assert decision.reason == f"{GTIN_VERSION}: GTIN 00036000291452"
    assert session.get_one(Listing, ean.id).match_confidence == Decimal("1.0000")
    assert (counts.gtin_linked, counts.gtin_queued, counts.scored) == (1, 0, 0)

    rows = [table(session, model) for model in (MatchCandidate, MatchDecision, Product)]
    again = world.run()
    assert (again.gtin_linked, again.gtin_queued) == (0, 0)
    assert [table(session, model) for model in (MatchCandidate, MatchDecision, Product)] == rows


def test_invalid_placeholder_and_reused_gtins_never_link(world: World) -> None:
    for code in ("036000291453", "123456789012", "212345678909"):  # check digit, placeholder, RCN
        for vendor in (world.store(), world.store()):
            world.barcode(world.listing(vendor, 0, embedded=False), code)
    reuser = world.store()
    for vendor in (reuser, reuser, world.store()):  # one store puts the GTIN on two listings
        world.barcode(world.listing(vendor, 0, embedded=False), "4006381333931")
    counts = world.run()
    session = world.session
    assert (counts.gtin_linked, counts.gtin_queued) == (0, 0)
    assert table(session, MatchCandidate) == table(session, MatchDecision) == []
    linked = select(func.count()).select_from(Listing).where(Listing.product_id.is_not(None))
    assert session.scalar(linked) == 0


@pytest.mark.parametrize("status", ["rejected", "split"])
def test_gtin_pairs_honour_manual_decisions_and_outrank_image_scores(
    world: World, status: str
) -> None:
    session = world.session
    # A rejected or split pair, and a third listing sharing their GTIN.
    a, b, bridge = (world.listing(world.store(), 0, embedded=False) for _ in range(3))
    # An owner unlinked this listing: it never moves.
    unlinked, partner = (world.listing(world.store(), 1, embedded=False) for _ in range(2))
    # Two products is a merge (M-5). Image neighbours in M-3's queue band, so M-3 sees them too.
    on_one = world.listing(world.store(), 2, product=world.product())
    on_other = world.listing(world.store(), 2, QUEUE_ANGLE, product=world.product())
    # M-3 queued this pair at 0.83 in an earlier run.
    queued = tuple(world.listing(world.store(), 3, embedded=False) for _ in range(2))
    for code, listings in (
        ("036000291452", (a, b, bridge)),
        ("4006381333931", (unlinked, partner)),
        ("96385074", (on_one, on_other)),
        ("10036000291459", queued),
    ):
        for listing in listings:
            world.barcode(listing, code)
    for (x, y), pair_status, score in (((a, b), status, "0.5"), (queued, "pending", "0.83")):
        low, high = sorted((x.id, y.id))
        session.add(
            MatchCandidate(
                listing_a_id=low,
                listing_b_id=high,
                score=Decimal(score),
                scorer_version="m3-older",
                status=pair_status,
            )
        )
    session.add(
        MatchDecision(
            actor="owner",
            action="unlink",
            listing_id=unlinked.id,
            from_product_id=world.product(),
            reason="manual",
        )
    )
    session.flush()
    decided = table(session, MatchCandidate)[0]
    merge_products = products(session, on_one, on_other)
    counts = world.run()

    assert table(session, MatchCandidate)[0] == decided
    # The bridge forms a product with one side; the other side never joins it.
    first, other, bridged = products(session, a, b, bridge)
    assert first is not None and first == bridged and other is None
    vetoed = candidate(session, b, bridge)
    assert vetoed is not None and (vetoed.status, vetoed.score) == ("pending", Decimal("1.0000"))
    assert products(session, unlinked, partner) == [None, None]
    assert candidate(session, unlinked, partner).status == "pending"  # type: ignore[union-attr]
    merge = candidate(session, on_one, on_other)
    assert merge is not None
    assert (merge.status, merge.score, merge.scorer_version) == (
        "pending",
        Decimal("1.0000"),
        GTIN_VERSION,
    )
    assert products(session, on_one, on_other) == merge_products
    outranked = candidate(session, *queued)
    assert outranked is not None
    assert (outranked.status, outranked.score, outranked.scorer_version) == (
        "accepted",
        Decimal("1.0000"),
        GTIN_VERSION,
    )
    q1, q2 = products(session, *queued)
    assert q1 is not None and q1 == q2
    algo = session.scalars(select(MatchDecision.listing_id).where(MatchDecision.actor == "algo"))
    assert sorted(algo) == sorted((a.id, bridge.id, *(listing.id for listing in queued)))
    assert (counts.gtin_linked, counts.gtin_queued) == (2, 3)

    rows = [table(session, model) for model in (MatchCandidate, MatchDecision, Product)]
    world.run()
    assert [table(session, model) for model in (MatchCandidate, MatchDecision, Product)] == rows
