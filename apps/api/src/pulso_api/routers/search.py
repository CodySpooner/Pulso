"""Global search for the Ctrl+K palette (UX-9, DEC-252): products, stores and suppliers. All
three are global market data, so auth applies and no workspace filter. Notes and tags (workspace
tables) are never searched."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime, BaseModel, StringConstraints
from sqlalchemy import (
    ColumnElement,
    Double,
    Row,
    ScalarSelect,
    Select,
    case,
    func,
    literal,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.orm import Session

from pulso_api.auth import current_principal
from pulso_api.dependencies import get_db
from pulso_api.routers.products import best_feature, is_stale
from pulso_core.models import Category, Listing, Product, Source, Store, Supplier

router = APIRouter(prefix="/v1/search", dependencies=[Depends(current_principal)])
DB = Annotated[Session, Depends(get_db)]
Kind = Literal["exact", "prefix", "substring", "fuzzy"]
KINDS: tuple[Kind, ...] = ("exact", "prefix", "substring", "fuzzy")


class Match(BaseModel):
    field: Literal["title", "listing_title", "domain", "myshopify_domain", "name"]
    text: str  # the value that matched: a merged product's or a listing's title can differ
    kind: Kind


class ProductHit(BaseModel):
    id: UUID  # the survivor when a merged product matched
    title: str
    category: str | None  # the taxonomy path; null while uncategorised
    match: Match


class StoreHit(BaseModel):
    id: int
    domain: str
    myshopify_domain: str | None
    match: Match
    last_crawled_at: AwareDatetime | None
    stale: bool  # last crawled more than twice the store crawler's interval ago
    top_product_id: UUID | None  # what the palette opens until a store page exists


class SupplierHit(BaseModel):
    id: int
    name: str
    platform: str  # suppliers.platform, e.g. "cj"
    match: Match
    top_product_id: UUID | None


class SearchResults(BaseModel):
    products: list[ProductHit]
    stores: list[StoreHit]
    suppliers: list[SupplierHit]
    catalog_empty: bool  # nothing matched because nothing has been collected yet


def matches(column: Any, q: str) -> ColumnElement[bool]:
    """A substring, or from 3 characters a word within pg_trgm's word similarity threshold (0.6),
    which catches one-letter typos. Both use the trigram indexes (migration 0008)."""
    substring: ColumnElement[bool] = column.icontains(q, autoescape=True)
    if len(q) < 3:  # two characters make one real trigram: fuzzy would be noise
        return substring
    return or_(substring, column.op("%>", is_comparison=True)(q))


def ranked(session: Session, q: str, limit: int, *candidates: Select[Any]) -> list[Row[Any]]:
    """The best match per key over (key, field, text, priority) candidates, best first: exact,
    prefix, substring, then fuzzy; within a kind the closer, then the shorter text."""
    c = union_all(*candidates).subquery()
    kind = case(
        (func.lower(c.c.text) == func.lower(q), 0),
        (c.c.text.istartswith(q, autoescape=True), 1),
        (c.c.text.icontains(q, autoescape=True), 2),
        else_=3,
    )
    similarity = func.word_similarity(q, c.c.text)
    best = (
        select(c.c.key, c.c.field, c.c.text, kind.label("kind"), similarity.label("similarity"))
        .distinct(c.c.key)
        .order_by(c.c.key, kind, similarity.desc(), c.c.priority, func.length(c.c.text))
        .subquery()
    )
    order = (best.c.kind, best.c.similarity.desc(), func.length(best.c.text), best.c.text)
    return list(session.execute(select(best).order_by(*order, best.c.key).limit(limit)))


def match(row: Row[Any]) -> Match:
    return Match(field=row.field, text=row.text, kind=KINDS[row.kind])


def top_product(vendor: ColumnElement[bool]) -> ScalarSelect[Any]:
    """The vendor's live listed product with the best 7-day growth (Discover's momentum,
    DEC-239), then the newest. A merged product resolves to its survivor."""
    feature = best_feature(Product.id).lateral()
    return (
        select(func.coalesce(Product.merged_into_id, Product.id))
        .select_from(Listing)
        .join(Product, Product.id == Listing.product_id)
        .outerjoin(feature, true())
        .where(vendor, Listing.delisted_at.is_(None))
        .order_by(
            func.coalesce(feature.c.growth, literal(float("-inf"), Double)).desc(),
            Product.first_seen_at.desc(),
            Product.id,
        )
        .limit(1)
        .scalar_subquery()
    )


def search_products(session: Session, q: str, limit: int) -> list[ProductHit]:
    # ponytail: one merge hop; a chained merge's middle product redirects again on its page.
    survivor = func.coalesce(Product.merged_into_id, Product.id).label("key")
    rows = ranked(
        session,
        q,
        limit,
        select(survivor, literal("title").label("field"), Product.name.label("text"))
        .add_columns(literal(0).label("priority"))
        .where(matches(Product.name, q), Product.status != "empty"),  # DEC-271
        select(survivor, literal("listing_title"), Listing.title, literal(1))
        .join(Product, Product.id == Listing.product_id)
        .where(Listing.delisted_at.is_(None), matches(Listing.title, q)),
    )
    products = {
        row.id: row
        for row in session.execute(
            select(Product.id, Product.name, Category.path)
            .outerjoin(Category, Category.id == Product.category_id)
            .where(Product.id.in_([row.key for row in rows]))
        )
    }
    return [
        ProductHit(
            id=row.key,
            title=products[row.key].name,
            category=products[row.key].path,
            match=match(row),
        )
        for row in rows
    ]


def search_stores(session: Session, q: str, limit: int, now: datetime) -> list[StoreHit]:
    rows = ranked(
        session,
        q,
        limit,
        select(Store.id.label("key"), literal("domain").label("field"), Store.domain.label("text"))
        .add_columns(literal(0).label("priority"))
        .where(matches(Store.domain, q)),
        select(Store.id, literal("myshopify_domain"), Store.myshopify_domain, literal(1)).where(
            matches(Store.myshopify_domain, q)
        ),
    )
    stores = {
        row.Store.id: row
        for row in session.execute(
            select(Store, top_product(Listing.store_id == Store.id).label("top")).where(
                Store.id.in_([row.key for row in rows])
            )
        )
    }
    # ponytail: every store is a Shopify store crawled by one source so far.
    config = session.scalar(select(Source.config).where(Source.key == "shopify_stores")) or {}
    hits = []
    for row in rows:
        store: Store = stores[row.key].Store
        crawled = store.last_crawled_at
        hits.append(
            StoreHit(
                id=store.id,
                domain=store.domain,
                myshopify_domain=store.myshopify_domain,
                match=match(row),
                last_crawled_at=crawled,
                stale=crawled is not None and is_stale(config, crawled, now),
                top_product_id=stores[row.key].top,
            )
        )
    return hits


def search_suppliers(session: Session, q: str, limit: int) -> list[SupplierHit]:
    rows = ranked(
        session,
        q,
        limit,
        select(Supplier.id.label("key"), literal("name").label("field"))
        .add_columns(Supplier.name.label("text"), literal(0).label("priority"))
        .where(matches(Supplier.name, q)),
    )
    suppliers = {
        row.Supplier.id: row
        for row in session.execute(
            select(Supplier, top_product(Listing.supplier_id == Supplier.id).label("top")).where(
                Supplier.id.in_([row.key for row in rows])
            )
        )
    }
    return [
        SupplierHit(
            id=row.key,
            name=suppliers[row.key].Supplier.name,
            platform=suppliers[row.key].Supplier.platform,
            match=match(row),
            top_product_id=suppliers[row.key].top,
        )
        for row in rows
    ]


@router.get("", response_model=SearchResults)
def search(
    session: DB,
    q: Annotated[
        str,
        # Postgres text can't hold NUL: a 422, not a 500 (XR-32).
        StringConstraints(strip_whitespace=True, max_length=100, pattern=r"^[^\x00]*$"),
        Query(description="Trimmed; under 2 characters returns no results. No NUL character."),
    ],
    limit: Annotated[int, Query(ge=1, le=20, description="Per group")] = 5,
) -> SearchResults:
    """Products (by title or a live listing's title), stores (by domain) and suppliers (by name),
    each group best first."""
    if len(q) < 2:
        return SearchResults(products=[], stores=[], suppliers=[], catalog_empty=False)
    products = search_products(session, q, limit)
    stores = search_stores(session, q, limit, datetime.now(UTC))
    suppliers = search_suppliers(session, q, limit)
    empty = not (products or stores or suppliers) and not session.scalar(
        select(
            or_(
                select(Product.id).exists(), select(Store.id).exists(), select(Supplier.id).exists()
            )
        )
    )
    return SearchResults(products=products, stores=stores, suppliers=suppliers, catalog_empty=empty)
