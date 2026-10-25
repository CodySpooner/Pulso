"""Saved screens (WF-1 part a, DEC-336): the workspace's named Screener definitions, each run
by passing its filters, sort and order to GET /v1/screener."""

import json
from typing import Annotated, Literal
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_api.auth import current_principal
from pulso_api.errors import APIError
from pulso_api.routers.products import DB, CurrentPrincipal
from pulso_api.routers.screener import Filters, SortKey
from pulso_api.schemas.text import NoNulStr
from pulso_core.models import SavedScreen as ScreenRow

router = APIRouter(prefix="/v1/screens", dependencies=[Depends(current_principal)])
# The stored definition's shape. A breaking change to Filters bumps it, and a migration
# rewrites the older rows (or the read upgrades them) before they validate again.
VERSION = 1
CURSOR = TypeAdapter(str)  # the last name: names are unique per workspace
Name = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Definition(BaseModel):
    """What a screen runs: GET /v1/screener's `filters`, `sort` and `order`."""

    model_config = ConfigDict(extra="forbid")
    filters: Filters = Field(default_factory=Filters)
    sort: SortKey = "trend"
    order: Literal["desc", "asc"] = "desc"


class ScreenIn(Definition):
    name: Name


class SavedScreen(Definition):
    id: UUID
    name: str
    version: int  # the definition's shape
    created_at: AwareDatetime


class SavedScreenPage(BaseModel):
    items: list[SavedScreen]  # by name
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


def read(row: ScreenRow) -> SavedScreen:
    return SavedScreen(
        **Definition.model_validate(row.definition).model_dump(),
        id=row.id,
        name=row.name,
        version=row.version,
        created_at=row.created_at,
    )


def owned(session: Session, workspace_id: UUID, screen_id: UUID) -> ScreenRow:
    """This workspace's screen. Another workspace's screen is a 404, like a missing one."""
    row = session.get(ScreenRow, screen_id)
    if row is None or row.workspace_id != workspace_id:
        raise APIError(404, "not_found", "Saved screen not found.")
    return row


@router.get("", response_model=SavedScreenPage)
def list_screens(
    principal: CurrentPrincipal,
    session: DB,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> SavedScreenPage:
    query = select(ScreenRow).where(ScreenRow.workspace_id == principal.workspace_id)
    if cursor is not None:
        try:
            after = CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid saved screen cursor.") from None
        query = query.where(ScreenRow.name > after)
    rows = session.scalars(query.order_by(ScreenRow.name).limit(limit + 1)).all()
    return SavedScreenPage(
        items=[read(row) for row in rows[:limit]],
        next_cursor=json.dumps(rows[limit - 1].name) if len(rows) > limit else None,
    )


@router.post("", response_model=SavedScreen, status_code=201)
def create_screen(body: ScreenIn, principal: CurrentPrincipal, session: DB) -> SavedScreen:
    """Save a definition under a name; a name the workspace already uses is a 409."""
    row = ScreenRow(
        workspace_id=principal.workspace_id,
        name=body.name,
        version=VERSION,
        definition=body.model_dump(mode="json", exclude={"name"}, exclude_none=True),
    )
    session.add(row)
    session.commit()
    return read(row)


@router.get("/{screen_id}", response_model=SavedScreen)
def get_screen(screen_id: UUID, principal: CurrentPrincipal, session: DB) -> SavedScreen:
    return read(owned(session, principal.workspace_id, screen_id))


@router.delete("/{screen_id}", response_model=SavedScreen)
def delete_screen(screen_id: UUID, principal: CurrentPrincipal, session: DB) -> SavedScreen:
    """Delete a screen; returns it as it was."""
    row = owned(session, principal.workspace_id, screen_id)
    removed = read(row)
    session.delete(row)
    session.commit()
    return removed
