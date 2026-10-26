"""Boards (WF-3 part a, DEC-319): the workspace's boards of product ideas. Cards keep a manual
order and a board-only note, and send-to-testing opens Idea tests through the Testing Board's
create path. Each card carries its stats, read for the whole page in a fixed number of queries
(imp-454), and `?format=csv` exports the cards as the JSON builds them (imp-456)."""

import json
import re
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from itertools import count
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
from sqlalchemy import ColumnElement, Row, Select, delete, func, select, tuple_
from sqlalchemy.orm import Session
from starlette.responses import Response

from pulso_api.auth import current_principal
from pulso_api.csv_export import csv_response, major
from pulso_api.errors import APIError
from pulso_api.routers.products import (
    DB,
    CurrentPrincipal,
    Incomplete,
    Margin,
    best_margins,
    latest_snapshots,
    listing_stats,
    margin_stat,
)
from pulso_api.routers.screener import LatestScore, score_value
from pulso_api.routers.testing import ProductTestCreate, ProductTestOut, create_test
from pulso_api.routers.watchlists import ItemsIn, Name, resolve, survivors
from pulso_api.schemas.provenance import NoSource, Sourced, Stat
from pulso_api.schemas.text import NoNulStr
from pulso_core.models import Board as BoardRow
from pulso_core.models import BoardItem as ItemRow
from pulso_core.models import Image, Product, ProductTest, Source
from pulso_core.models.core import TEST_STAGES
from pulso_core.scores import Kind
from pulso_ml.scores import opportunity as op

router = APIRouter(prefix="/v1/boards", dependencies=[Depends(current_principal)])
ITEM_CURSOR = TypeAdapter(tuple[int, UUID])
Prose = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, max_length=10_000)]
# The board table's columns in its order, plus the ids and an as-of per stat (DEC-350).
BOARD_CSV = (
    "position",
    "product_id",
    "product",
    "price_min",
    "price_max",
    "currency",
    "best_margin",
    "best_margin_pct",
    "trend",
    "lifecycle",
    "saturation",
    "note",
    "merged_into_id",
    "added_at",
    "price_as_of",
    "best_margin_as_of",
    "trend_as_of",
    "lifecycle_as_of",
    "saturation_as_of",
    "stale",
)


class BoardIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    description: Prose | None = None


class BoardPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    description: Prose | None = None  # null clears it


class Board(BaseModel):
    id: UUID
    name: str
    description: str | None
    archived_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime  # bumped by every write to the board or its items
    item_count: int


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    position: Annotated[int, Field(ge=0)] | None = None  # 0 is first; past the end is last
    note: Prose | None = None  # null clears it


class BoardItem(BaseModel):
    product_id: UUID
    name: str
    image_url: str | None
    position: int
    note: str | None
    added_at: AwareDatetime
    # The survivor, when the product was merged after the add: cards aren't rewritten (DEC-319
    # e), so the card keeps its product and shows the survivor's stats below.
    merged_into_id: UUID | None
    currency: Literal["USD"]  # of the *_minor stats
    price_min_minor: Stat  # Discover's price range: the live USD store listings'
    price_max_minor: Stat
    best_margin_minor: Margin | Incomplete  # Discover's best landed margin, this workspace's
    trend: LatestScore | NoSource  # the newest stored rows, as the Screener reads them
    saturation: LatestScore | NoSource
    lifecycle: LatestScore | NoSource


class BoardItemPage(BaseModel):
    items: list[BoardItem]  # by position
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


class ItemsAdded(BaseModel):
    added: list[UUID]  # appended in the order given; a merged product adds its survivor
    skipped: list[UUID]  # already on the board


class SentToTesting(BaseModel):
    created: list[ProductTestOut]  # one Idea test per product
    skipped: list[UUID]  # the product already has an open test


def boards(session: Session, workspace_id: UUID, *where: ColumnElement[bool]) -> list[Board]:
    """The workspace's boards, most recently active first, each with its item count."""
    count = select(func.count()).where(ItemRow.board_id == BoardRow.id).scalar_subquery()
    query = select(
        BoardRow.id,
        BoardRow.name,
        BoardRow.description,
        BoardRow.archived_at,
        BoardRow.created_at,
        BoardRow.updated_at,
        count.label("item_count"),
    ).where(BoardRow.workspace_id == workspace_id, *where)
    rows = session.execute(query.order_by(BoardRow.updated_at.desc(), BoardRow.id))
    return [Board.model_validate(row, from_attributes=True) for row in rows]


def owned(session: Session, workspace_id: UUID, board_id: UUID, *, write: bool = False) -> BoardRow:
    """This workspace's board. Another workspace's board is a 404, like a missing one. A write
    bumps updated_at, whether it changes the board or only its items."""
    row = session.get(BoardRow, board_id)
    if row is None or row.workspace_id != workspace_id:
        raise APIError(404, "not_found", "Board not found.")
    if write:
        row.updated_at = func.now()
    return row


def cards(
    board_id: UUID,
) -> Select[tuple[UUID, str, str, int, str | None, datetime]]:
    return (
        select(
            ItemRow.product_id,
            Product.name,
            Image.url.label("image_url"),
            ItemRow.position,
            ItemRow.note,
            ItemRow.added_at,
        )
        .join(Product, Product.id == ItemRow.product_id)
        .outerjoin(Image, Image.id == Product.main_image_id)
        .where(ItemRow.board_id == board_id)
    )


def with_stats(session: Session, workspace_id: UUID, rows: Sequence[Row[Any]]) -> list[BoardItem]:
    """`cards` rows with their stats: one query per part for any number of cards, through the
    reads Discover and the Screener use (the margin only through the economics view)."""
    into = resolve(session, [row.product_id for row in rows])
    products = list(set(into.values()))
    snapshots = latest_snapshots(session, products)
    margins = best_margins(session, workspace_id, products)
    kinds: tuple[Kind, ...] = ("trend", "saturation", "lifecycle")
    scores = {kind: op.latest_rows(session, kind, products) for kind in kinds}
    sources = {source.key: source for source in session.scalars(select(Source))}
    now = datetime.now(UTC)
    items = []
    for row in rows:
        survivor = into[row.product_id]
        prices = listing_stats(snapshots[survivor], now)
        items.append(
            BoardItem(
                **row._mapping,
                merged_into_id=None if survivor == row.product_id else survivor,
                currency="USD",
                price_min_minor=prices["price_min_minor"],
                price_max_minor=prices["price_max_minor"],
                best_margin_minor=margin_stat(margins.get(survivor), sources, now),
                **{kind: score_value(scores[kind].get(survivor)) for kind in kinds},
            )
        )
    return items


def csv_rows(
    session: Session, workspace_id: UUID, chunk: Sequence[Row[Any]], places: Iterator[int]
) -> Iterator[list[object]]:
    """One export chunk as BOARD_CSV cells: the cards `with_stats` builds for the JSON, each at
    its 1-based place, as the table's # shows it. A stat with nothing behind it is a blank."""
    for each in with_stats(session, workspace_id, chunk):
        low, high, margin = each.price_min_minor, each.price_max_minor, each.best_margin_minor
        stats = (low, margin, each.trend, each.lifecycle, each.saturation)
        yield [
            next(places),
            each.product_id,
            each.name,
            major(low.value),
            major(high.value),
            each.currency,
            major(margin.value),
            Decimal(margin.margin_bps).scaleb(-2) if isinstance(margin, Margin) else None,
            each.trend.value,
            getattr(each.lifecycle, "stage", None),
            each.saturation.value,
            each.note,
            each.merged_into_id,
            each.added_at,
            *(getattr(stat, "as_of", None) for stat in stats),
            any(isinstance(stat, Sourced) and stat.stale for stat in (low, high, margin)),
        ]


@router.get("", response_model=list[Board])
def list_boards(principal: CurrentPrincipal, session: DB, archived: bool = False) -> list[Board]:
    """The active boards, or with `archived=true` the archived ones. Not paged: the index shows
    them all."""
    shown = BoardRow.archived_at.is_not(None) if archived else BoardRow.archived_at.is_(None)
    return boards(session, principal.workspace_id, shown)


@router.post("", response_model=Board, status_code=201)
def create_board(body: BoardIn, principal: CurrentPrincipal, session: DB) -> Board:
    """An empty board. A name the workspace already uses, archived boards included, is a 409."""
    row = BoardRow(workspace_id=principal.workspace_id, **body.model_dump())
    session.add(row)
    session.commit()
    return boards(session, principal.workspace_id, BoardRow.id == row.id)[0]


@router.patch("/{board_id}", response_model=Board)
def update_board(
    board_id: UUID, body: BoardPatch, principal: CurrentPrincipal, session: DB
) -> Board:
    """Rename the board or rewrite its description. A duplicate name is a 409."""
    row = owned(session, principal.workspace_id, board_id, write=True)
    if body.name is not None:
        row.name = body.name
    if "description" in body.model_fields_set:
        row.description = body.description
    session.commit()
    return boards(session, principal.workspace_id, BoardRow.id == board_id)[0]


@router.post("/{board_id}/archive", response_model=Board)
def archive_board(board_id: UUID, principal: CurrentPrincipal, session: DB) -> Board:
    """Move the board behind the archived filter, items and all. Again keeps the first
    archived_at."""
    row = owned(session, principal.workspace_id, board_id, write=True)
    if row.archived_at is None:
        row.archived_at = func.now()
    session.commit()
    return boards(session, principal.workspace_id, BoardRow.id == board_id)[0]


@router.post("/{board_id}/unarchive", response_model=Board)
def unarchive_board(board_id: UUID, principal: CurrentPrincipal, session: DB) -> Board:
    owned(session, principal.workspace_id, board_id, write=True).archived_at = None
    session.commit()
    return boards(session, principal.workspace_id, BoardRow.id == board_id)[0]


@router.delete("/{board_id}", response_model=Board)
def delete_board(board_id: UUID, principal: CurrentPrincipal, session: DB) -> Board:
    """Delete the board and its cards; the products and their tests stay. Returns the board as
    it was, with the number of cards removed."""
    row = owned(session, principal.workspace_id, board_id)
    removed = boards(session, principal.workspace_id, BoardRow.id == board_id)[0]
    session.delete(row)
    session.commit()
    return removed


@router.get(
    "/{board_id}/items",
    response_model=BoardItemPage,
    responses={
        200: {
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "JSON, or with format=csv every card as a CSV download.",
        },
    },
)
def list_board_items(
    board_id: UUID,
    principal: CurrentPrincipal,
    session: DB,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    format: Annotated[
        Literal["json", "csv"],
        Query(description="csv: every card in board order, no cursor or limit (DEC-350)"),
    ] = "json",
) -> BoardItemPage | Response:
    """The cards in board order, `product_id` breaking ties, each with its stats."""
    board = owned(session, principal.workspace_id, board_id)
    query = cards(board_id)
    if format == "csv":
        # Named after the board in ASCII, so the header stays plain: pulso_board_q4-gifts_<date>.
        slug = re.sub(r"[^a-z0-9]+", "-", board.name.lower()).strip("-")[:60].rstrip("-")
        places = count(1)
        return csv_response(
            session,
            f"board_{slug}" if slug else "board",
            BOARD_CSV,
            query.order_by(ItemRow.position, ItemRow.product_id),
            lambda chunk: csv_rows(session, principal.workspace_id, chunk, places),
        )
    if cursor is not None:
        try:
            after = ITEM_CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid board item cursor.") from None
        query = query.where(tuple_(ItemRow.position, ItemRow.product_id) > after)
    rows = session.execute(
        query.order_by(ItemRow.position, ItemRow.product_id).limit(limit + 1)
    ).all()
    last = rows[limit - 1] if len(rows) > limit else None
    return BoardItemPage(
        items=with_stats(session, principal.workspace_id, rows[:limit]),
        next_cursor=json.dumps([last.position, str(last.product_id)]) if last else None,
    )


@router.post("/{board_id}/items", response_model=ItemsAdded)
def add_board_items(
    board_id: UUID, body: ItemsIn, principal: CurrentPrincipal, session: DB
) -> ItemsAdded:
    """Append products after the last card, in the order given. A merged product adds its
    survivor; one already on the board keeps its place and note. An unknown id is a 404."""
    owned(session, principal.workspace_id, board_id, write=True)
    ids = survivors(session, body.product_ids)
    on_board = set(
        session.scalars(
            select(ItemRow.product_id).where(
                ItemRow.board_id == board_id, ItemRow.product_id.in_(ids)
            )
        )
    )
    added = [p for p in ids if p not in on_board]
    end = session.scalars(
        select(func.coalesce(func.max(ItemRow.position) + 1, 0)).where(ItemRow.board_id == board_id)
    ).one()
    session.add_all(
        ItemRow(
            workspace_id=principal.workspace_id,
            board_id=board_id,
            product_id=product_id,
            position=end + i,
        )
        for i, product_id in enumerate(added)
    )
    session.commit()
    return ItemsAdded(added=added, skipped=[p for p in ids if p in on_board])


@router.patch("/{board_id}/items/{product_id}", response_model=BoardItem)
def update_board_item(
    board_id: UUID, product_id: UUID, body: ItemPatch, principal: CurrentPrincipal, session: DB
) -> BoardItem:
    """Write the card's note, or move it to `position`; the cards then number 0, 1, 2… in
    order."""
    owned(session, principal.workspace_id, board_id, write=True)
    item = session.get(ItemRow, (board_id, product_id))
    if item is None:
        raise APIError(404, "not_found", "The product is not on this board.")
    if "note" in body.model_fields_set:
        item.note = body.note
    if body.position is not None:
        # ponytail: a move renumbers every card, one UPDATE each. Past ~500 cards a board wants
        # fractional indexing (a sortable key between the two neighbours, one UPDATE per move).
        order = list(
            session.scalars(
                select(ItemRow)
                .where(ItemRow.board_id == board_id, ItemRow.product_id != product_id)
                .order_by(ItemRow.position, ItemRow.product_id)
            )
        )
        order.insert(body.position, item)
        for position, each in enumerate(order):
            each.position = position
    session.commit()
    row = session.execute(cards(board_id).where(ItemRow.product_id == product_id)).one()
    return with_stats(session, principal.workspace_id, [row])[0]


@router.delete("/{board_id}/items/{product_id}", response_model=Board)
def remove_board_item(
    board_id: UUID, product_id: UUID, principal: CurrentPrincipal, session: DB
) -> Board:
    """Take a product off the board, note and all; one not on it changes nothing. The other
    cards keep their order. Returns the board."""
    owned(session, principal.workspace_id, board_id, write=True)
    session.execute(
        delete(ItemRow).where(ItemRow.board_id == board_id, ItemRow.product_id == product_id)
    )
    session.commit()
    return boards(session, principal.workspace_id, BoardRow.id == board_id)[0]


@router.post("/{board_id}/items/send-to-testing", response_model=SentToTesting)
def send_board_items_to_testing(
    board_id: UUID, body: ItemsIn, principal: CurrentPrincipal, session: DB
) -> SentToTesting:
    """Open one Idea test per product through `create_test`. A merged product sends its
    survivor; one with an open test (Idea, Researching or Testing) is skipped."""
    workspace_id = principal.workspace_id
    owned(session, workspace_id, board_id, write=True)
    ids = survivors(session, body.product_ids)
    tested = set(
        session.scalars(
            select(ProductTest.product_id).where(
                ProductTest.workspace_id == workspace_id,
                ProductTest.product_id.in_(ids),
                ProductTest.stage.in_(TEST_STAGES[:3]),  # uq_product_tests_open's stages
            )
        )
    )
    created = [
        create_test(ProductTestCreate(product_id=p), principal, session)
        for p in ids
        if p not in tested
    ]
    session.commit()
    return SentToTesting(created=created, skipped=[p for p in ids if p in tested])
