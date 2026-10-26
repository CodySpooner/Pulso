"""Alerts (WF-4 parts a, a2, b and d, DEC-324, DEC-330, DEC-333, DEC-353): the in-app inbox, its
archive and the workspace's rules. `pulso_core.alerts.evaluate()` fires the alerts; the web shows
them in the top bar's bell and on /alerts."""

from collections.abc import Sequence
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.exceptions import RequestValidationError
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from sqlalchemy import func, select, tuple_, update
from sqlalchemy.orm import Session

from pulso_api.errors import APIError
from pulso_api.routers.products import DB, CurrentPrincipal, live_product
from pulso_api.schemas.text import NoNulStr
from pulso_core.alerts import SCORED, SPIKE
from pulso_core.models import Alert, AlertRule, Listing, Product, Watchlist

router = APIRouter(prefix="/v1/alerts")
rules_router = APIRouter(prefix="/v1/alert-rules")
ALERT_CURSOR = TypeAdapter(tuple[AwareDatetime, int])
RULE_CURSOR = TypeAdapter(tuple[AwareDatetime, UUID])
RuleType = Literal[
    "supplier_price_change",
    "freight_change",
    "supplier_stock_out",
    "back_in_stock",
    "velocity_spike",
    "saturation_cross",
]
Name = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Ids = Annotated[
    list[Annotated[int, Field(ge=1, le=2**63 - 1)]], Field(min_length=1, max_length=500)
]
Limit = Annotated[int, Query(ge=1, le=100)]
NOT_NULL = ("name", "params", "enabled")
EXTRA = ("product_id", "product_name", "watchlist_name", "last_fired_at")  # not columns
# Each type's params and defaults; None is required. Supplier rules take {"pct": 5}.
PARAMS: dict[str, dict[str, Any]] = {
    "velocity_spike": SPIKE,
    "saturation_cross": {"threshold": None, "direction": None},
}


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rule_id: UUID | None  # null for system alerts and when the rule was deleted
    type: str
    entity_type: str
    entity_id: str
    fired_at: AwareDatetime
    payload: dict[str, Any] = Field(
        description="old and new: {value, currency (money), as_of}, new also source and "
        "raw_payload_id; threshold; as_of per source; link: the entity's page."
    )
    read_at: AwareDatetime | None


class AlertPage(BaseModel):
    items: list[AlertOut]  # newest first; archived alerts list only with archived=true
    next_cursor: str | None = Field(description="Pass as `cursor` with the same filters.")


class UnreadCount(BaseModel):
    count: int  # unread and not archived


class ReadIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: Ids | None = None
    all: bool = False

    @model_validator(mode="after")
    def ids_or_all(self) -> Self:
        if (self.ids is not None) == self.all:
            raise ValueError("send ids or all: true, not both")
        return self


class ArchiveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: Ids


class Params(BaseModel):
    """Each rule type takes its own; another type's is a 422, and a missing one its default."""

    model_config = ConfigDict(extra="forbid")
    pct: Annotated[float, Field(gt=0, le=1000)] | None = Field(
        None,
        description="Price and freight: the ± % change from the reference (default 5). "
        "velocity_spike: the % rise of 7-day velocity over the prior 7 days (default 50).",
    )
    window_days: Literal[7] | None = Field(
        None, description="velocity_spike: 7, the 7 days against the 7 before (default)."
    )
    min_volume: Annotated[float, Field(ge=0, le=1_000_000)] | None = Field(
        None, description="velocity_spike: the units over 7 days it needs to fire (default 10)."
    )
    threshold: Annotated[float, Field(ge=0, le=100)] | None = Field(
        None, description="saturation_cross, required: the Saturation Score line, 0-100."
    )
    direction: Literal["above", "below"] | None = Field(
        None, description="saturation_cross, required: the side of the line that fires."
    )


class RulePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name | None = None
    params: Params | None = None
    enabled: bool | None = None
    muted_until: AwareDatetime | None = Field(None, description="Null unmutes.")


class RuleIn(RulePatch):
    name: Name
    type: RuleType
    target_type: Literal["product", "supplier_offer", "watchlist"] = Field(
        description="Supplier rules: product or supplier_offer. Score rules: product or watchlist."
    )
    target_id: str = Field(max_length=40, description="The product's, listing's or watchlist's id.")
    params: Params = Params()
    enabled: bool = True


class RuleOut(BaseModel):
    id: UUID
    name: str
    type: str
    target_type: str
    target_id: str | None
    params: dict[str, Any]
    enabled: bool
    muted_until: AwareDatetime | None
    armed: bool  # false while anything the rule watches sits past its threshold
    status: Literal["ok", "no_source", "skipped"] | None = Field(
        description="The last evaluation: no_source when nothing the rule watches has data yet, "
        "skipped when a collection gap held back a crossing; null before the first."
    )
    skipped: dict[str, Any] | None = Field(description='{"reason": "gap", "from", "to"}')
    last_evaluated_at: AwareDatetime | None
    created_at: AwareDatetime
    product_id: UUID | None = Field(
        description="The product the target is or belongs to; null for the Testing defaults "
        "and watchlists."
    )
    product_name: str | None
    watchlist_name: str | None = Field(description="A watchlist target's name.")
    last_fired_at: AwareDatetime | None = Field(
        description="The rule's newest alert, archived too."
    )


class RulePage(BaseModel):
    items: list[RuleOut]  # newest first
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


def unread(session: Session, workspace_id: UUID) -> UnreadCount:
    count = session.scalar(
        select(func.count()).where(
            Alert.workspace_id == workspace_id, Alert.read_at.is_(None), Alert.archived_at.is_(None)
        )
    )
    return UnreadCount(count=count or 0)


def mine(session: Session, workspace_id: UUID, ids: list[int]) -> None:
    """404 unless every id is one of the workspace's alerts, so a write changes all or nothing."""
    found = session.scalars(
        select(Alert.id).where(Alert.workspace_id == workspace_id, Alert.id.in_(ids))
    ).all()
    if len(found) != len(set(ids)):
        raise APIError(404, "not_found", "Alert not found.")


def archive(session: Session, workspace_id: UUID, ids: list[int], on: bool) -> UnreadCount:
    """Archive (keeping the first archive time) or unarchive; read state stays as it was."""
    mine(session, workspace_id, ids)
    session.execute(
        update(Alert)
        .where(Alert.workspace_id == workspace_id, Alert.id.in_(ids))
        .where(Alert.archived_at.is_(None) if on else Alert.archived_at.is_not(None))
        .values(archived_at=func.now() if on else None)
    )
    session.commit()
    return unread(session, workspace_id)


def views(session: Session, workspace_id: UUID, rows: Sequence[AlertRule]) -> list[RuleOut]:
    """Each rule with its target's product (a supplier offer's through its listing) and its newest
    alert. ponytail: a group-by over the workspace's alerts; index alerts (rule_id, fired_at) if
    an inbox ever grows past a few thousand."""
    offers = [int(str(row.target_id)) for row in rows if row.target_type == "supplier_offer"]
    listed = select(Listing.id, Listing.product_id).where(Listing.id.in_(offers))
    of_offer = dict(session.execute(listed).tuples().all())
    product = {
        row.id: of_offer.get(int(str(row.target_id)))
        if row.target_type == "supplier_offer"
        else UUID(str(row.target_id))
        for row in rows
        if row.target_type in ("product", "supplier_offer")
    }
    named = select(Product.id, Product.name).where(Product.id.in_(set(product.values()) - {None}))
    fired = (
        select(Alert.rule_id, func.max(Alert.fired_at))
        .where(Alert.workspace_id == workspace_id, Alert.rule_id.in_([row.id for row in rows]))
        .group_by(Alert.rule_id)
    )
    lists = [UUID(str(row.target_id)) for row in rows if row.target_type == "watchlist"]
    titled = select(Watchlist.id, Watchlist.name).where(Watchlist.id.in_(lists))
    names, last_fired, list_names = (
        dict(session.execute(named).tuples().all()),
        dict(session.execute(fired).tuples().all()),
        dict(session.execute(titled).tuples().all()),
    )
    fields = RuleOut.model_fields.keys() - {"status", "skipped", *EXTRA}
    return [
        RuleOut(
            **{name: getattr(row, name) for name in fields},
            status=(row.last_value or {}).get("status"),
            skipped=(row.last_value or {}).get("skipped"),
            product_id=product.get(row.id),
            product_name=names.get(product.get(row.id)),  # type: ignore[arg-type]
            watchlist_name=list_names.get(UUID(str(row.target_id)))
            if row.target_type == "watchlist"
            else None,
            last_fired_at=last_fired.get(row.id),
        )
        for row in rows
    ]


def owned(session: Session, workspace_id: UUID, rule_id: UUID) -> AlertRule:
    row = session.get(AlertRule, rule_id)
    if row is None or row.workspace_id != workspace_id:
        raise APIError(404, "not_found", "Alert rule not found.")
    return row


def checked(kind: str, params: Params) -> dict[str, Any]:
    """The type's params with its defaults; another type's param, or a missing required one,
    is a 422 on that field."""
    given = params.model_dump(exclude_none=True)
    fields = PARAMS.get(kind, {"pct": 5})
    errors = [
        {"loc": ("body", "params", name), "msg": "Not a param of this rule type", "type": "extra"}
        for name in sorted(given.keys() - fields.keys())
    ] + [
        {"loc": ("body", "params", name), "msg": "Field required", "type": "missing"}
        for name, default in fields.items()
        if default is None and name not in given
    ]
    if errors:
        raise RequestValidationError(errors)
    return fields | given


def target(session: Session, workspace_id: UUID, body: RuleIn) -> str:
    """The rule's target id, normalized, once the product, supplier offer or watchlist exists."""
    allowed = ("product", "watchlist") if body.type in SCORED else ("product", "supplier_offer")
    if body.target_type not in allowed:
        raise APIError(422, "target_type", f"A {body.type} rule watches a {' or '.join(allowed)}.")
    try:
        key = int(body.target_id) if body.target_type == "supplier_offer" else UUID(body.target_id)
    except ValueError:
        raise APIError(422, "target_id", "target_id is not an id of target_type.") from None
    if body.target_type == "watchlist":
        listed = session.get(Watchlist, key)
        if listed is None or listed.workspace_id != workspace_id:
            raise APIError(404, "not_found", "Watchlist not found.")
    elif isinstance(key, UUID):
        live_product(session, key)
    elif not 0 < key < 2**63 or getattr(session.get(Listing, key), "supplier_id", None) is None:
        raise APIError(404, "not_found", "Supplier offer not found.")
    return str(key)


@router.get("", response_model=AlertPage)
def list_alerts(
    principal: CurrentPrincipal,
    session: DB,
    unread: bool | None = None,
    archived: bool = False,
    kind: Annotated[str | None, Query(alias="type", max_length=40)] = None,
    cursor: str | None = None,
    limit: Limit = 50,
) -> AlertPage:
    query = select(Alert).where(
        Alert.workspace_id == principal.workspace_id,
        Alert.archived_at.is_not(None) if archived else Alert.archived_at.is_(None),
    )
    if unread is not None:
        query = query.where(Alert.read_at.is_(None) if unread else Alert.read_at.is_not(None))
    if kind is not None:
        query = query.where(Alert.type == kind)
    if cursor is not None:
        try:
            query = query.where(
                tuple_(Alert.fired_at, Alert.id) < ALERT_CURSOR.validate_json(cursor)
            )
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid alerts cursor.") from None
    rows = session.scalars(
        query.order_by(Alert.fired_at.desc(), Alert.id.desc()).limit(limit + 1)
    ).all()
    last = rows[limit - 1] if len(rows) > limit else None
    return AlertPage(
        items=[AlertOut.model_validate(row) for row in rows[:limit]],
        next_cursor=ALERT_CURSOR.dump_json((last.fired_at, last.id)).decode() if last else None,
    )


@router.get("/unread-count", response_model=UnreadCount)
def count_unread_alerts(principal: CurrentPrincipal, session: DB) -> UnreadCount:
    return unread(session, principal.workspace_id)


@router.post("/read", response_model=UnreadCount)
def read_alerts(body: ReadIn, principal: CurrentPrincipal, session: DB) -> UnreadCount:
    """Mark the alerts read (the first read time is kept); returns the unread count."""
    query = update(Alert).where(
        Alert.workspace_id == principal.workspace_id, Alert.read_at.is_(None)
    )
    if body.ids is not None:
        mine(session, principal.workspace_id, body.ids)
        query = query.where(Alert.id.in_(body.ids))
    session.execute(query.values(read_at=func.now()))
    session.commit()
    return unread(session, principal.workspace_id)


@router.post("/archive", response_model=UnreadCount)
def archive_alerts(body: ArchiveIn, principal: CurrentPrincipal, session: DB) -> UnreadCount:
    return archive(session, principal.workspace_id, body.ids, on=True)


@router.post("/unarchive", response_model=UnreadCount)
def unarchive_alerts(body: ArchiveIn, principal: CurrentPrincipal, session: DB) -> UnreadCount:
    """Move archived alerts back to the inbox; returns the unread count."""
    return archive(session, principal.workspace_id, body.ids, on=False)


@rules_router.get("", response_model=RulePage)
def list_alert_rules(
    principal: CurrentPrincipal, session: DB, cursor: str | None = None, limit: Limit = 50
) -> RulePage:
    query = select(AlertRule).where(AlertRule.workspace_id == principal.workspace_id)
    if cursor is not None:
        try:
            after = RULE_CURSOR.validate_json(cursor)
        except ValidationError:
            raise APIError(422, "invalid_cursor", "Invalid alert rules cursor.") from None
        query = query.where(tuple_(AlertRule.created_at, AlertRule.id) < after)
    order = (AlertRule.created_at.desc(), AlertRule.id.desc())
    rows = session.scalars(query.order_by(*order).limit(limit + 1)).all()
    last = rows[limit - 1] if len(rows) > limit else None
    return RulePage(
        items=views(session, principal.workspace_id, rows[:limit]),
        next_cursor=RULE_CURSOR.dump_json((last.created_at, last.id)).decode() if last else None,
    )


@rules_router.post("", response_model=RuleOut, status_code=201)
def create_alert_rule(body: RuleIn, principal: CurrentPrincipal, session: DB) -> RuleOut:
    values = body.model_dump() | {
        "target_id": target(session, principal.workspace_id, body),
        "params": checked(body.type, body.params),
    }
    row = AlertRule(workspace_id=principal.workspace_id, **values)
    session.add(row)
    session.commit()
    return views(session, principal.workspace_id, [row])[0]


@rules_router.patch("/{rule_id}", response_model=RuleOut)
def update_alert_rule(
    rule_id: UUID, patch: RulePatch, principal: CurrentPrincipal, session: DB
) -> RuleOut:
    row = owned(session, principal.workspace_id, rule_id)
    values = patch.model_dump(exclude_unset=True)
    if any(values.get(name, 0) is None for name in NOT_NULL):
        raise APIError(422, "validation_error", f"{', '.join(NOT_NULL)} cannot be null.")
    if patch.params is not None:
        values["params"] = checked(row.type, patch.params)
    for name, value in values.items():
        setattr(row, name, value)
    session.commit()
    return views(session, principal.workspace_id, [row])[0]


@rules_router.delete("/{rule_id}", response_model=RuleOut)
def delete_alert_rule(rule_id: UUID, principal: CurrentPrincipal, session: DB) -> RuleOut:
    """Delete the rule and return it as it was; its alerts stay, with a null rule_id."""
    row = owned(session, principal.workspace_id, rule_id)
    if row.target_type == "test":
        raise APIError(409, "default_rule", "Disable or mute a Testing default; it can't go.")
    deleted = views(session, principal.workspace_id, [row])[0]
    session.delete(row)
    session.commit()
    return deleted
