"""Watchlists (WF-2 part a, DEC-314): the workspace's named product lists. A star (the ★ toggle
and `W`) adds to the list named "Main", created by the first star. Rows show the product as
Discover reads it and the first added_at; sparklines, "since added" deltas and the summary
come later."""

import json
from typing import Annotated
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
from sqlalchemy import ScalarSelect, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import (
    DB,
    MAIN,
    CurrentPrincipal,
    DiscoverItem,
    discover_items,
    with_merged,
)
from pulso_api.schemas.text import NoNulStr
from pulso_core.models import Image, Product
from pulso_core.models import Watchlist as ListRow
from pulso_core.models import WatchlistItem as ItemRow

router = APIRouter(prefix="/v1/watchlists", dependencies=[Depends(current_principal)])
products_router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
ORDER = (ListRow.position, ListRow.created_at, ListRow.id)
ITEM_CURSOR = TypeAdapter(tuple[AwareDatetime, UUID])
Name = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class WatchlistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name


class WatchlistPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    position: Annotated[int, Field(ge=0)] | None = None  # 0 is first; past the end is last


class Watchlist(BaseModel):
    id: UUID
    name: str
    position: int
    created_at: AwareDatetime
    item_count: int


class ItemsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: Annotated[list[UUID], Field(min_length=1, max_length=100)]


class ItemsMove(ItemsIn):
    to: UUID  # the list they move to


class WatchlistItem(BaseModel):
    product_id: UUID
    name: str
    image_url: str | None
    added_at: AwareDatetime  # the first add, kept through re-adds and moves
    # The product now, as Discover reads it. One merged after the add reads as its survivor,
    # so product.id differs from product_id: the UI's "merged" note (DEC-314 d, DEC-322).
    product: DiscoverItem


class WatchlistItemPage(BaseModel):
    items: list[WatchlistItem]  # newest first
    next_cursor: str | None = Field(description="Pass as `cursor` for the next, older page.")


class Watched(BaseModel):
    watchlist_id: UUID  # "Main"
    product_id: UUID  # the surviving product when the id given was merged
    added_at: AwareDatetime


def lists(
    session: Session, workspace_id: UUID, watchlist_id: UUID | None = None
) -> list[Watchlist]:
    """The workspace's lists in sub-nav order, each with its item count."""
    count = select(func.count()).where(ItemRow.watchlist_id == ListRow.id).scalar_subquery()
    query = select(
        ListRow.id, ListRow.name, ListRow.position, ListRow.created_at, count.label("item_count")
    ).where(ListRow.workspace_id == workspace_id)
    if watchlist_id is not None:
        query = query.where(ListRow.id == watchlist_id)
    rows = session.execute(query.order_by(*ORDER))
    return [Watchlist.model_validate(row, from_attributes=True) for row in rows]


def owned(session: Session, workspace_id: UUID, watchlist_id: UUID) -> ListRow:
    """This workspace's list. Another workspace's list is a 404, like a missing one."""
    row = session.get(ListRow, watchlist_id)
    if row is None or row.workspace_id != workspace_id:
        raise APIError(404, "not_found", "Watchlist not found.")
    return row


def last_position(workspace_id: UUID) -> ScalarSelect[int]:
    return (
        select(func.coalesce(func.max(ListRow.position) + 1, 0))
        .where(ListRow.workspace_id == workspace_id)
        .scalar_subquery()
    )


def resolve(session: Session, product_ids: list[UUID]) -> dict[UUID, UUID]:
    """Each product's survivor: itself, or the product it was merged into through any chain of
    merges (DEC-263). An unknown id is a 404."""
    merged_into: dict[UUID, UUID | None] = {}
    todo = set(product_ids)
    while todo:
        rows = (
            session.execute(select(Product.id, Product.merged_into_id).where(Product.id.in_(todo)))
            .tuples()
            .all()
        )
        if len(rows) < len(todo):
            raise APIError(404, "not_found", "Product not found.")
        merged_into.update(rows)
        todo = {into for _, into in rows if into is not None} - merged_into.keys()

    def survivor(product_id: UUID) -> UUID:
        while (into := merged_into[product_id]) is not None:
            product_id = into
        return product_id

    return {product_id: survivor(product_id) for product_id in product_ids}


def survivors(session: Session, product_ids: list[UUID]) -> list[UUID]:
    """Each product's survivor, once each."""
    return list(dict.fromkeys(resolve(session, product_ids).values()))


@router.get("", response_model=list[Watchlist])
def list_watchlists(principal: CurrentPrincipal, session: DB) -> list[Watchlist]:
    """Every list, by position then oldest first. Not paged: the sub-nav shows them all."""
    return lists(session, principal.workspace_id)


@router.post("", response_model=Watchlist, status_code=201)
def create_watchlist(body: WatchlistIn, principal: CurrentPrincipal, session: DB) -> Watchlist:
    """An empty list, placed last. A name the workspace already uses is a 409."""
    workspace_id = principal.workspace_id
    new_id = session.scalars(
        insert(ListRow)
        .values(workspace_id=workspace_id, name=body.name, position=last_position(workspace_id))
        .returning(ListRow.id)
    ).one()
    session.commit()
    return lists(session, workspace_id, new_id)[0]


@router.patch("/{watchlist_id}", response_model=Watchlist)
def update_watchlist(
    watchlist_id: UUID, body: WatchlistPatch, principal: CurrentPrincipal, session: DB
) -> Watchlist:
    """Rename a list, or move it to `position`; the lists then number 0, 1, 2… in order."""
    row = owned(session, principal.workspace_id, watchlist_id)
    if body.name is not None:
        row.name = body.name
    if body.position is not None:
        order = list(
            session.scalars(
                select(ListRow)
                .where(ListRow.workspace_id == principal.workspace_id, ListRow.id != row.id)
                .order_by(*ORDER)
            )
        )
        order.insert(body.position, row)
        for position, each in enumerate(order):
            each.position = position
    session.commit()
    return lists(session, principal.workspace_id, watchlist_id)[0]


@router.delete("/{watchlist_id}", response_model=Watchlist)
def delete_watchlist(watchlist_id: UUID, principal: CurrentPrincipal, session: DB) -> Watchlist:
    """Delete a list and its items; the products stay on any other list. Returns the list as it
    was, with the number of items removed."""
    row = owned(session, principal.workspace_id, watchlist_id)
    removed = lists(session, principal.workspace_id, watchlist_id)[0]
    session.delete(row)
    session.commit()
    return removed


@router.get("/{watchlist_id}/items", response_model=WatchlistItemPage)
def list_watchlist_items(
    watchlist_id: UUID,
    principal: CurrentPrincipal,
    session: DB,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> WatchlistItemPage:
    owned(session, principal.workspace_id, watchlist_id)
    query = (
        select(ItemRow.product_id, Product.name, Image.url.label("image_url"), ItemRow.added_at)
        .join(Product, Product.id == ItemRow.product_id)
        .outerjoin(Image, Image.id == Product.main_image_id)
        .where(ItemRow.watchlist_id == watchlist_id)
    )
    if cursor is not None:
        try:
            after = ITEM_CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid watchlist item cursor.") from None
        query = query.where(tuple_(ItemRow.added_at, ItemRow.product_id) < after)
    rows = session.execute(
        query.order_by(ItemRow.added_at.desc(), ItemRow.product_id.desc()).limit(limit + 1)
    ).all()
    last = rows[limit - 1] if len(rows) > limit else None
    into = resolve(session, [row.product_id for row in rows[:limit]])
    products = discover_items(session, principal.workspace_id, list(set(into.values())))
    return WatchlistItemPage(
        items=[
            WatchlistItem(**row._mapping, product=products[into[row.product_id]])
            for row in rows[:limit]
        ],
        next_cursor=json.dumps([last.added_at.isoformat(), str(last.product_id)]) if last else None,
    )


@router.post("/{watchlist_id}/items", response_model=Watchlist)
def add_watchlist_items(
    watchlist_id: UUID, body: ItemsIn, principal: CurrentPrincipal, session: DB
) -> Watchlist:
    """Add products; a merged one adds its survivor. One already on the list keeps its first
    added_at. Returns the list."""
    owned(session, principal.workspace_id, watchlist_id)
    rows = [
        {"workspace_id": principal.workspace_id, "watchlist_id": watchlist_id, "product_id": p}
        for p in survivors(session, body.product_ids)
    ]
    session.execute(insert(ItemRow).values(rows).on_conflict_do_nothing())
    session.commit()
    return lists(session, principal.workspace_id, watchlist_id)[0]


@router.delete("/{watchlist_id}/items/{product_id}", response_model=Watchlist)
def remove_watchlist_item(
    watchlist_id: UUID, product_id: UUID, principal: CurrentPrincipal, session: DB
) -> Watchlist:
    """Take a product off the list; one not on it changes nothing. Returns the list."""
    owned(session, principal.workspace_id, watchlist_id)
    session.execute(
        delete(ItemRow).where(
            ItemRow.watchlist_id == watchlist_id, ItemRow.product_id == product_id
        )
    )
    session.commit()
    return lists(session, principal.workspace_id, watchlist_id)[0]


@router.post("/{watchlist_id}/items/move", response_model=Watchlist)
def move_watchlist_items(
    watchlist_id: UUID, body: ItemsMove, principal: CurrentPrincipal, session: DB
) -> Watchlist:
    """Move products to the list `to`, each keeping its first added_at (the earlier one when
    `to` already holds it). Products not on this list are skipped. Returns `to`."""
    owned(session, principal.workspace_id, watchlist_id)
    owned(session, principal.workspace_id, body.to)
    if body.to != watchlist_id:
        moved = session.execute(
            delete(ItemRow)
            .where(ItemRow.watchlist_id == watchlist_id, ItemRow.product_id.in_(body.product_ids))
            .returning(ItemRow.product_id, ItemRow.added_at)
        ).all()
        if moved:
            stmt = insert(ItemRow).values(
                [
                    {
                        "workspace_id": principal.workspace_id,
                        "watchlist_id": body.to,
                        "product_id": row.product_id,
                        "added_at": row.added_at,
                    }
                    for row in moved
                ]
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["watchlist_id", "product_id"],
                    set_={"added_at": func.least(ItemRow.added_at, stmt.excluded.added_at)},
                )
            )
    session.commit()
    return lists(session, principal.workspace_id, body.to)[0]


@products_router.put("/{product_id}/watch", response_model=Watched)
def watch_product(product_id: UUID, principal: CurrentPrincipal, session: DB) -> Watched:
    """Star a product: add it to "Main", which the first star creates (placed last). A merged
    product stars its survivor. Starring again changes nothing."""
    workspace_id = principal.workspace_id
    [survivor] = survivors(session, [product_id])
    session.execute(
        insert(ListRow)
        .values(workspace_id=workspace_id, name=MAIN, position=last_position(workspace_id))
        .on_conflict_do_nothing()
    )
    main = session.scalars(
        select(ListRow.id).where(ListRow.workspace_id == workspace_id, ListRow.name == MAIN)
    ).one()
    item = {"workspace_id": workspace_id, "watchlist_id": main, "product_id": survivor}
    session.execute(insert(ItemRow).values(item).on_conflict_do_nothing())
    session.commit()
    added_at = session.scalars(
        select(ItemRow.added_at).where(ItemRow.watchlist_id == main, ItemRow.product_id == survivor)
    ).one()
    return Watched(watchlist_id=main, product_id=survivor, added_at=added_at)


@products_router.delete("/{product_id}/watch", response_model=Watched | None)
def unwatch_product(product_id: UUID, principal: CurrentPrincipal, session: DB) -> Watched | None:
    """Unstar a product: take it, and any product merged into it, off "Main". Returns the item
    removed, or null when "Main" didn't hold it."""
    main = select(ListRow.id).where(
        ListRow.workspace_id == principal.workspace_id, ListRow.name == MAIN
    )
    removed = session.execute(
        delete(ItemRow)
        .where(ItemRow.watchlist_id.in_(main), ItemRow.product_id.in_(with_merged(product_id)))
        .returning(ItemRow.watchlist_id, ItemRow.product_id, ItemRow.added_at)
    ).all()
    session.commit()
    return Watched.model_validate(removed[0], from_attributes=True) if removed else None
