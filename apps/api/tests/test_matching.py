from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import (
    Category,
    CollectorRun,
    Image,
    Listing,
    ListingSnapshot,
    ListingVariant,
    MatchCandidate,
    MatchDecision,
    Product,
    ProductNote,
    ProductTag,
    RawPayload,
    Store,
    Supplier,
    User,
    Workspace,
)
from pulso_core.models.catalog import EMBEDDING_DIM
from pulso_ml.matching.matcher import match
from pulso_ml.matching.score import CONFIG

# The Matching Queue API (UX-1, DEC-263) on fixture rows: global match tables, workspace context.

pytestmark = pytest.mark.db
SHOPIFY, CJ = 1, 2  # sources seeded by migration 0001
SEEN = datetime(2026, 10, 1, tzinfo=UTC)


def vector(axis: int) -> list[float]:
    values = [0.0] * EMBEDDING_DIM
    values[axis] = 1.0
    return values


@dataclass
class Queue:
    engine: Engine
    as_: Callable[[str], TestClient]
    workspaces: dict[str, UUID]
    users: dict[str, UUID]
    payload: int
    n: int = 0
    ids: dict[str, Any] = field(default_factory=dict)

    def listing(
        self,
        session: Session,
        source: int,
        *,
        product: UUID | None = None,
        images: int = 1,
        price: int | None = 1000,
        axis: int | None = None,
    ) -> Listing:
        self.n += 1
        if source == CJ:
            vendor: dict[str, int] = {"supplier_id": self.supplier(session)}
        else:
            store = Store(domain=f"store{self.n}.example", platform="shopify")
            session.add(store)
            session.flush()
            vendor = {"store_id": store.id}
        listing = Listing(
            source_id=source,
            external_id=f"x{self.n}",
            url=f"https://example.test/{self.n}",
            title=f"Sunset lamp {self.n}",
            product_id=product,
            first_seen_at=SEEN + timedelta(days=self.n),
            title_embedding=None if axis is None else vector(axis),
            **vendor,
        )
        session.add(listing)
        session.flush()
        for position in range(1, images + 1):
            session.add(
                Image(
                    listing_id=listing.id,
                    url=f"https://cdn.example.test/{self.n}-{position}.jpg",
                    position=position,
                    phash=-1,
                    embedding=None if axis is None else vector(axis),
                )
            )
        if price is not None:
            session.add(
                ListingSnapshot(
                    listing_id=listing.id,
                    observed_for=date(2026, 10, 24),
                    raw_payload_id=self.payload,
                    values_hash=f"{self.n:064}",
                    price_min_minor=price,
                    price_max_minor=price + 500,
                    currency="USD",
                )
            )
        session.flush()
        return listing

    def supplier(self, session: Session) -> int:
        supplier = Supplier(platform="cj", external_id=f"s{self.n}", name=f"CJ supplier {self.n}")
        session.add(supplier)
        session.flush()
        return supplier.id

    @staticmethod
    def pair(
        session: Session,
        x: Listing,
        y: Listing,
        score: str,
        status: str = "pending",
        version: str = CONFIG.version,
    ) -> int:
        low, high = sorted((x.id, y.id))
        candidate = MatchCandidate(
            listing_a_id=low,
            listing_b_id=high,
            score=Decimal(score),
            image_cos=Decimal(score),
            title_cos=None,
            phash_sim=Decimal("0.9"),
            price_sane=True,
            scorer_version=version,
            status=status,
        )
        session.add(candidate)
        session.flush()
        return candidate.id

    def decisions(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(MatchDecision)) or 0


@pytest.fixture
def queue(client: TestClient, db_engine: Engine) -> Iterator[Queue]:
    with Session(db_engine) as session:
        users = {key: User(clerk_user_id=f"user_{key}") for key in "ab"}
        workspaces = {key: Workspace(name=f"Workspace {key}") for key in "ab"}
        run = CollectorRun(source_id=CJ, trigger="manual", status="success")
        session.add_all([*users.values(), *workspaces.values(), run])
        session.flush()
        payload = RawPayload(source_id=CJ, run_id=run.id, request={}, bytes=1, sha256="0" * 64)
        session.add(payload)
        session.commit()
        principals = {key: Principal(users[key].id, workspaces[key].id) for key in "ab"}
        ids = (
            {key: w.id for key, w in workspaces.items()},
            {key: u.id for key, u in users.items()},
            payload.id,
        )

    def database() -> Iterator[Session]:
        with Session(db_engine) as session:
            yield session

    assert isinstance(client.app, FastAPI)
    app = client.app
    app.dependency_overrides[get_db] = database

    def as_(key: str) -> TestClient:
        app.dependency_overrides[current_principal] = lambda: principals[key]
        return client

    yield Queue(db_engine, as_, *ids)


def seed_queue(q: Queue) -> dict[str, int]:
    """Three pending pairs (one on a product workspace A has noted), and two that never queue."""
    with Session(q.engine) as session:
        noted = Product(name="Noted lamp", first_seen_at=SEEN)
        session.add(noted)
        session.flush()
        on_noted = q.listing(session, SHOPIFY, product=noted.id)
        cj = [q.listing(session, CJ, images=5) for _ in range(3)]
        shop = [q.listing(session, SHOPIFY, price=None, images=0) for _ in range(2)]
        ids = {
            "high": q.pair(session, cj[0], shop[0], "0.8900"),
            "noted": q.pair(session, cj[1], on_noted, "0.7600", version="gtin-1"),
            "middle": q.pair(session, cj[2], shop[1], "0.8000"),
            "decided": q.pair(session, cj[0], shop[1], "0.9500", status="rejected"),
        }
        twin = q.listing(session, SHOPIFY, product=noted.id)
        ids["same_product"] = q.pair(session, on_noted, twin, "0.8500")  # already one product
        session.add_all(
            [
                ProductNote(
                    workspace_id=q.workspaces["a"],
                    product_id=noted.id,
                    author_id=q.users["a"],
                    body="watch this",
                ),
                ProductTag(workspace_id=q.workspaces["a"], product_id=noted.id, tag="Q4"),
            ]
        )
        session.commit()
        q.ids["noted_product"] = noted.id
        return ids


def test_queue_sorts_filters_and_pages_pending_pairs(queue: Queue) -> None:
    ids = seed_queue(queue)
    url = "/v1/admin/matching/candidates"
    a = queue.as_("a")  # as_ switches the one client's principal
    page = a.get(url).json()
    assert [item["id"] for item in page["items"]] == [ids["noted"], ids["high"], ids["middle"]]
    assert [item["impact"] for item in page["items"]] == [True, False, False]
    first = page["items"][1]
    assert (first["score"], first["scorer_version"]) == (0.89, CONFIG.version)
    assert {first["a"]["source"], first["b"]["source"]} == {"cj", "shopify_stores"}
    assert first["a"]["image_url"] is not None or first["b"]["image_url"] is not None
    assert page["summary"] == {
        "pending": 3,
        "stored_sources": ["cj", "shopify_stores"],
        "auto_linked": 0,
        "last_auto_link_at": None,
        "matcher_enabled": False,
    }
    assert page["facets"] == {
        "source_pairs": ["cj+shopify_stores"],
        "versions": sorted([CONFIG.version, "gtin-1"]),
    }
    assert page["thresholds"]["auto_link"] == 0.9 and page["thresholds"]["queue"] == 0.75

    # Workspace B has no context: impact is false everywhere, so score order.
    other = queue.as_("b").get(url).json()["items"]
    assert [item["id"] for item in other] == [ids["high"], ids["middle"], ids["noted"]]
    assert not any(item["impact"] for item in other)

    def walk(**params: Any) -> list[int]:
        seen, cursor = [], None
        while True:
            page = {**params, "limit": 1} | ({"cursor": cursor} if cursor else {})
            body = queue.as_("a").get(url, params=page).json()
            seen += [item["id"] for item in body["items"]]
            if (cursor := body["next_cursor"]) is None:
                return seen

    assert walk() == [ids["noted"], ids["high"], ids["middle"]]
    assert walk(sort="score") == [ids["high"], ids["middle"], ids["noted"]]
    assert walk(sort="age") == sorted([ids["high"], ids["noted"], ids["middle"]])

    def filtered(**params: Any) -> list[int]:
        return [item["id"] for item in queue.as_("a").get(url, params=params).json()["items"]]

    assert filtered(version="gtin-1") == [ids["noted"]]
    assert filtered(min_score="0.79", max_score="0.89") == [ids["middle"]]
    assert filtered(source_pair="shopify_stores+cj") == filtered()
    assert filtered(source_pair="cj+google_trends") == []
    a = queue.as_("a")
    assert a.get(url, params={"cursor": "[1"}).status_code == 422
    assert a.get(url, params={"source_pair": "cj"}).status_code == 422


def test_candidate_detail_shows_both_listings_components_and_workspace_counts(
    queue: Queue,
) -> None:
    ids = seed_queue(queue)
    url = f"/v1/admin/matching/candidates/{ids['noted']}"
    detail = queue.as_("a").get(url).json()
    assert (detail["status"], detail["superseded"], detail["score"]) == ("pending", False, 0.76)
    assert (detail["image_cos"], detail["title_cos"], detail["phash_sim"]) == (0.76, None, 0.9)
    cj, shop = sorted((detail["a"], detail["b"]), key=lambda side: side["source"])
    assert (cj["source_name"], cj["vendor_kind"], len(cj["images"])) == (
        "CJ Dropshipping",
        "supplier",
        4,
    )
    assert cj["price"]["min_minor"] == 1000 and cj["price"]["currency"] == "USD"
    assert shop["vendor"].endswith(".example") and shop["vendor_kind"] == "store"
    (cluster,) = detail["clusters"]
    assert cluster["product_id"] == str(queue.ids["noted_product"])
    assert (cluster["listings"], len(cluster["members"]), cluster["notes"], cluster["tags"]) == (
        2,
        2,
        1,
        1,
    )
    # Two workspaces: B sees the same global pair, none of A's notes or tags.
    (theirs,) = queue.as_("b").get(url).json()["clusters"]
    assert (theirs["notes"], theirs["tags"]) == (0, 0)
    same = queue.as_("a").get(f"/v1/admin/matching/candidates/{ids['same_product']}").json()
    assert same["superseded"] is True
    assert queue.as_("a").get("/v1/admin/matching/candidates/999999").status_code == 404


def test_decisions_only_append_and_undo_adds_compensating_rows(queue: Queue) -> None:
    ids = seed_queue(queue)
    client, url = queue.as_("a"), "/v1/admin/matching/decisions"
    counts = [queue.decisions()]

    accepted = client.post(url, json={"action": "accept", "candidate_id": ids["high"]})
    assert accepted.status_code == 201
    body = accepted.json()
    assert body["action"] == "accept" and len(body["listing_ids"]) == 2 and body["id"]
    counts.append(queue.decisions())
    detail = client.get(f"/v1/admin/matching/candidates/{ids['high']}").json()
    assert detail["superseded"] is True
    twice = client.post(url, json={"action": "accept", "candidate_id": ids["high"]})
    assert (twice.status_code, twice.json()["code"]) == (409, "decision_conflict")

    undone = client.post(f"{url}/{body['id']}/undo")
    assert undone.status_code == 201 and sorted(undone.json()["listing_ids"]) == sorted(
        body["listing_ids"]
    )
    counts.append(queue.decisions())
    assert client.get(f"/v1/admin/matching/candidates/{ids['high']}").json()["status"] == "pending"
    assert client.post(f"{url}/{body['id']}/undo").status_code == 409
    assert client.post(f"{url}/999999/undo").status_code == 404

    rejected = client.post(url, json={"action": "reject", "candidate_id": ids["middle"]})
    assert rejected.status_code == 201 and rejected.json()["product_id"] is None
    counts.append(queue.decisions())

    # Merge the accepted pair's product into the noted one, then split and unlink.
    again = client.post(url, json={"action": "accept", "candidate_id": ids["high"]}).json()
    merged = client.post(
        url,
        json={
            "action": "merge",
            "product_id": again["product_id"],
            "into": str(queue.ids["noted_product"]),
        },
    )
    assert merged.status_code == 201 and merged.json()["product_id"] == str(
        queue.ids["noted_product"]
    )
    counts += [queue.decisions()]
    moved = merged.json()["listing_ids"]
    split = client.post(url, json={"action": "split", "listing_ids": moved[:1]})
    assert split.status_code == 201 and split.json()["product_id"] not in (
        None,
        again["product_id"],
    )
    unlink = client.post(url, json={"action": "unlink", "listing_ids": moved[1:2]})
    assert unlink.status_code == 201 and unlink.json()["product_id"] is None
    counts.append(queue.decisions())
    assert client.post(url, json={"action": "unlink", "listing_ids": [999999]}).status_code == 409
    assert client.post(url, json={"action": "skip", "candidate_id": ids["high"]}).status_code == 422
    assert client.post(url, json={"action": "accept", "candidate_id": 999999}).status_code == 404
    assert counts == sorted(counts) and len(set(counts)) == len(counts)  # only ever grows
    with Session(queue.engine) as session:
        actors = set(session.scalars(select(MatchDecision.actor)))
        assert actors == {str(queue.users["a"])}


def test_a_product_emptied_by_an_undo_leaves_discover_search_and_its_page(queue: Queue) -> None:
    """Undoing an accept that formed a product, or a split onto a new one, empties it (DEC-271)."""
    with Session(queue.engine) as session:
        cj, shop = queue.listing(session, CJ), queue.listing(session, SHOPIFY)
        pair = queue.pair(session, cj, shop, "0.8000")
        kept = Product(name="Kept lamp", first_seen_at=SEEN)
        session.add_all([kept, Category(id=7, name="Lamps", path="Home > Lamps")])
        session.flush()
        leaves = [queue.listing(session, SHOPIFY, product=kept.id) for _ in range(2)][1].id
        session.commit()
        kept_id = str(kept.id)
    client, url = queue.as_("a"), "/v1/admin/matching/decisions"

    def listed() -> tuple[set[str], set[str], list[int]]:
        discover = client.get("/v1/products").json()["items"]
        search = client.get("/v1/search", params={"q": "Sunset lamp"}).json()["products"]
        used = client.get("/v1/categories").json()
        return {i["id"] for i in discover}, {h["id"] for h in search}, [c["id"] for c in used]

    emptied = []
    for body in (
        {"action": "accept", "candidate_id": pair},
        {"action": "split", "listing_ids": [leaves]},
    ):
        decision = client.post(url, json=body).json()
        with Session(queue.engine) as session:  # the taxonomy job categorised it meanwhile
            session.get_one(Product, UUID(decision["product_id"])).category_id = 7
            session.commit()
        discover, search, used = listed()
        assert decision["product_id"] in discover & search and used == [7]
        assert client.get(f"/v1/products/{decision['product_id']}").status_code == 200
        assert client.post(f"{url}/{decision['id']}/undo").status_code == 201
        emptied.append(decision["product_id"])

    assert listed() == ({kept_id}, {kept_id}, [])
    for product_id in emptied:
        page = client.get(f"/v1/products/{product_id}")
        assert (page.status_code, page.json()["code"]) == (404, "no_listings")


def test_a_split_or_rejected_pair_stays_apart_after_a_matcher_rerun(queue: Queue) -> None:
    """Decided through the API, then the matcher's GTIN and score passes run again at 1.0."""
    with Session(queue.engine) as session:
        cost = queue.listing(session, CJ, axis=0)
        shops = [queue.listing(session, SHOPIFY, price=2500, axis=0) for _ in range(2)]
        # A 25x markup: 1.0 by image but an insane price, so it queues and never auto-links.
        cheap, retail = (
            queue.listing(session, CJ, price=100, axis=1),
            queue.listing(session, SHOPIFY, price=2500, axis=1),
        )
        for listing in (cost, *shops):
            session.add(
                ListingVariant(
                    listing_id=listing.id, external_id=f"v{listing.id}", barcode="4006381333931"
                )
            )
        session.commit()
        odd, cost_id, cheap_id, retail_id = shops[1].id, cost.id, cheap.id, retail.id

    def rerun() -> dict[int, UUID | None]:
        with Session(queue.engine) as session:
            match(session, lambda *_: None)
            return dict(session.execute(select(Listing.id, Listing.product_id)).tuples().all())

    linked = rerun()
    assert linked[cost_id] is not None and linked[cost_id] == linked[odd]
    client, url = queue.as_("a"), "/v1/admin/matching/decisions"
    split = client.post(url, json={"action": "split", "listing_ids": [odd]}).json()
    (pair,) = client.get("/v1/admin/matching/candidates").json()["items"]
    assert {pair["a"]["listing_id"], pair["b"]["listing_id"]} == {cheap_id, retail_id}
    assert (
        client.post(url, json={"action": "reject", "candidate_id": pair["id"]}).status_code == 201
    )

    count = queue.decisions()
    after = rerun()
    assert str(after[odd]) == split["product_id"] != str(after[cost_id])  # still split
    assert (after[cheap_id], after[retail_id]) == (None, None)  # still apart
    assert queue.decisions() == count  # the re-run wrote no decision
    with Session(queue.engine) as session:
        assert session.get_one(MatchCandidate, pair["id"]).status == "rejected"


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/v1/admin/matching/candidates", None),
        ("GET", "/v1/admin/matching/candidates/1", None),
        ("POST", "/v1/admin/matching/decisions", {"action": "reject", "candidate_id": 1}),
        ("POST", "/v1/admin/matching/decisions/1/undo", None),
    ],
)
def test_matching_routes_reject_non_admins(
    client: TestClient,
    signed_token: Callable[[dict[str, Any]], str],
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> None:
    token = signed_token({"sub": "user_other"})
    response = client.request(method, path, json=body, headers={"Authorization": "Bearer " + token})
    assert (response.status_code, response.json()["code"]) == (403, "not_allowlisted")
