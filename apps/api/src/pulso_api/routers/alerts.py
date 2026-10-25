"""Alert rules (WF-4 part a, DEC-324): the workspace's rules, which `pulso_core.alerts.evaluate()`
fires. The inbox endpoints are WF-4a2; the bell and /alerts UI are WF-4b."""

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    ValidationError,
)
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from pulso_api.errors import APIError
from pulso_api.routers.products import DB, CurrentPrincipal, live_product
from pulso_api.schemas.text import NoNulStr
from pulso_core.models import AlertRule, Listing

rules_router = APIRouter(prefix="/v1/alert-rules")
RULE_CURSOR = TypeAdapter(tuple[AwareDatetime, UUID])
RuleType = Literal["supplier_price_change", "freight_change", "supplier_stock_out", "back_in_stock"]
Name = Annotated[NoNulStr, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Limit = Annotated[int, Query(ge=1, le=100)]
NOT_NULL = ("name", "params", "enabled")


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pct: Annotated[float, Field(gt=0, le=1000)] = Field(
        5, description="The ± % change from the reference that fires a price or freight rule."
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
    target_type: Literal["product", "supplier_offer"]
    target_id: str = Field(max_length=40, description="The product's id or the listing's id.")
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


class RulePage(BaseModel):
    items: list[RuleOut]  # newest first
    next_cursor: str | None = Field(description="Pass as `cursor` for the next page.")


def view(row: AlertRule) -> RuleOut:
    last = row.last_value or {}
    fields = RuleOut.model_fields.keys() - {"status", "skipped"}
    return RuleOut(
        **{name: getattr(row, name) for name in fields},
        status=last.get("status"),
        skipped=last.get("skipped"),
    )


def owned(session: Session, workspace_id: UUID, rule_id: UUID) -> AlertRule:
    row = session.get(AlertRule, rule_id)
    if row is None or row.workspace_id != workspace_id:
        raise APIError(404, "not_found", "Alert rule not found.")
    return row


def target(session: Session, body: RuleIn) -> str:
    """The rule's target id, normalized, once the product or supplier offer exists."""
    try:
        key = UUID(body.target_id) if body.target_type == "product" else int(body.target_id)
    except ValueError:
        raise APIError(422, "target_id", "target_id is not an id of target_type.") from None
    if isinstance(key, UUID):
        live_product(session, key)
    elif not 0 < key < 2**63 or getattr(session.get(Listing, key), "supplier_id", None) is None:
        raise APIError(404, "not_found", "Supplier offer not found.")
    return str(key)


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
        items=[view(row) for row in rows[:limit]],
        next_cursor=RULE_CURSOR.dump_json((last.created_at, last.id)).decode() if last else None,
    )


@rules_router.post("", response_model=RuleOut, status_code=201)
def create_alert_rule(body: RuleIn, principal: CurrentPrincipal, session: DB) -> RuleOut:
    values = body.model_dump() | {"target_id": target(session, body)}
    row = AlertRule(workspace_id=principal.workspace_id, **values)
    session.add(row)
    session.commit()
    return view(row)


@rules_router.patch("/{rule_id}", response_model=RuleOut)
def update_alert_rule(
    rule_id: UUID, patch: RulePatch, principal: CurrentPrincipal, session: DB
) -> RuleOut:
    row = owned(session, principal.workspace_id, rule_id)
    values = patch.model_dump(exclude_unset=True)
    if any(values.get(name, 0) is None for name in NOT_NULL):
        raise APIError(422, "validation_error", f"{', '.join(NOT_NULL)} cannot be null.")
    for name, value in values.items():
        setattr(row, name, value)
    session.commit()
    return view(row)


@rules_router.delete("/{rule_id}", response_model=RuleOut)
def delete_alert_rule(rule_id: UUID, principal: CurrentPrincipal, session: DB) -> RuleOut:
    """Delete the rule and return it as it was; its alerts stay, with a null rule_id."""
    row = owned(session, principal.workspace_id, rule_id)
    if row.target_type == "test":
        raise APIError(409, "default_rule", "Disable or mute a Testing default; it can't go.")
    deleted = view(row)
    session.delete(row)
    session.commit()
    return deleted
