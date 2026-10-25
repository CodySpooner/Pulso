"""Testing Board (WF-5 part a, DEC-312): the workspace's product tests. CPA and ROAS are
computed on read, never stored; the start snapshot keeps the economics a test began with (R-21).
The stop-loss signal and "changed since start" are computed on read too (DEC-340)."""

from datetime import UTC, date, datetime
from fractions import Fraction
from typing import Annotated, Any, Literal, get_args
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_api.routers.account import MinorUnits
from pulso_api.routers.products import live_product
from pulso_api.routers.profit import ProfitCalcRequest, ProfitScenario, calc_profit
from pulso_api.schemas.text import NoNulStr
from pulso_core.models import Image, Product, ProductTest

router = APIRouter(prefix="/v1/tests")
CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
DB = Annotated[Session, Depends(get_db)]
TestId = Annotated[int, Path(ge=1, le=2**63 - 1)]
Stage = Literal["idea", "researching", "testing", "winner", "killed"]
KillReason = Literal[
    "no_sales_over_stop_loss",
    "cpa_above_break_even",
    "low_ctr_creatives",
    "supplier_issue",
    "sample_quality",
    "margin_too_thin",
    "saturated",
    "ad_account_rejection",
    "other",
]
ENDED = {"winner", "killed"}
NOT_NULL = {"stage", "ad_spend_minor", "revenue_minor", "orders", "scenario"}
# ponytail: v0 constants (DEC-340); k and N editable in Settings is a follow-up
STOP_LOSS_K = 2  # x break-even CPA: the no-order stop-loss and the suggested test budget
WINNER_ORDERS = 5  # N: orders before CPA is judged against break-even
NO_BREAK_EVEN = "Set price and supplier to compute break-even."
Signal = Literal["over_stop_loss", "winner_candidate"]
# "Changed since start": the scenario's inputs and lines a fresh calc can move, then the result.
Compared = Literal[
    "price_minor",
    "freight_quote_id",
    "goods_minor",
    "freight_minor",
    "duty_bps",
    "customs_fee_minor",
    "payment_fee_bps",
    "payment_fee_fixed_minor",
    "shopify_fee_bps",
    "returns_bps",
    "ad_cost_minor",
    "margin_minor",
]


class ProductTestPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: Stage | None = Field(
        None,
        description="Entering Testing sets started_on and takes the start snapshot; entering "
        "Winner or Killed sets ended_on; reopening clears ended_on (and the kill reason).",
    )
    started_on: date | None = Field(None, description="UTC calendar date.")
    ended_on: date | None = Field(None, description="UTC calendar date.")
    ad_spend_minor: MinorUnits | None = None  # USD, as are revenue_minor and the computed CPA
    revenue_minor: MinorUnits | None = None
    orders: Annotated[int, Field(ge=0, le=2**31 - 1, strict=True)] | None = None
    notes: (
        Annotated[NoNulStr, StringConstraints(strip_whitespace=True, max_length=10_000)] | None
    ) = None
    kill_reason: KillReason | None = Field(None, description="Required for Killed, and only then.")
    scenario: ProfitScenario | None = Field(
        None,
        description="The Profit calc to snapshot when the test first enters Testing. "
        "Omitted: the default scenario, as the Profit tab opens.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(value.get(key, 0) is None for key in NOT_NULL):
            raise ValueError(f"{', '.join(sorted(NOT_NULL))} cannot be null")
        return value


class ProductTestCreate(ProductTestPatch):
    product_id: UUID


class ProductTestOut(BaseModel):
    id: int
    product_id: UUID
    product_title: str  # the product's name and main image, for the board's card
    product_image_url: str | None
    stage: Stage
    started_on: date | None
    ended_on: date | None
    currency: Literal["USD"]  # of every *_minor field
    ad_spend_minor: int
    revenue_minor: int
    orders: int
    cpa_minor: int | None = Field(
        description="ad_spend_minor / orders, half-even to the cent; null with no orders."
    )
    roas: float | None = Field(description="revenue_minor / ad_spend_minor; null with no spend.")
    notes: str | None
    kill_reason: KillReason | None
    start_snapshot: dict[str, Any] | None = Field(
        description="The Profit calc (ProfitCalc fields plus captured_at) when the test first "
        "entered Testing. Never rewritten; null until then."
    )
    break_even_cpa_minor: int | None = Field(
        description="The start snapshot's margin before ads; null without a complete snapshot."
    )
    stop_loss_minor: int | None = Field(
        description=f"k x break-even CPA (k = {STOP_LOSS_K}): the no-order stop-loss line and "
        "the suggested test budget; null without a positive break-even CPA."
    )
    signal: Signal | None = Field(
        description="While Testing: over_stop_loss when orders = 0 and spend >= k x break-even "
        f"CPA, or orders >= N (N = {WINNER_ORDERS}) and cpa_minor > break-even CPA; "
        "winner_candidate when orders >= N and cpa_minor <= break-even CPA."
    )
    signal_reason: str | None = Field(description="While Testing, why there is no break-even.")
    created_at: AwareDatetime
    updated_at: AwareDatetime


class Change(BaseModel):
    input: Compared
    old: int | None  # the start snapshot's
    new: int | None  # the fresh calc's


class SinceStart(BaseModel):
    changes: list[Change] = Field(
        description="Each compared input the fresh calc differs on; empty: no changes since start."
    )
    reason: str | None = Field(description="Why the fresh calc couldn't run; `changes` is empty.")
    as_of: AwareDatetime | None = Field(description="The fresh calc's oldest observation.")


class ProductTestDetail(ProductTestOut):
    since_start: SinceStart | None = Field(
        description="The start snapshot against a fresh Profit calc of the same scenario (R-21); "
        "null before the test has a snapshot."
    )


class ProductTestPage(BaseModel):
    items: list[ProductTestOut]  # newest first
    next_cursor: int | None = Field(description="Pass as `cursor` with the same filter.")
    kill_reasons: dict[KillReason, int] = Field(
        description="Killed tests per reason, over the whole workspace (R-24)."
    )


# A test's product name and main image: the board lists them with one query, not one per card.
CARD = (Product.name, Image.url)
COMPUTED = {"cpa_minor", "roas", "product_title", "product_image_url"} | {
    "break_even_cpa_minor",
    "stop_loss_minor",
    "signal",
    "signal_reason",
}


def with_card[Q: Select[Any]](query: Q) -> Q:
    return (
        query.select_from(ProductTest)
        .join(Product, Product.id == ProductTest.product_id)
        .outerjoin(Image, Image.id == Product.main_image_id)
    )


def stop_loss(
    stage: str, snapshot: dict[str, Any] | None, spend: int, orders: int, cpa: int | None
) -> dict[str, Any]:
    """Break-even CPA from the start snapshot, k x it, and the Testing signal (vault Features/
    Testing Board, stop-loss rules). Integer cents: CPA is the half-even cent the card shows."""
    be: int | None = snapshot.get("margin_minor") if snapshot else None  # complete only (R-16)
    signal = None
    if be is not None and stage == "testing":
        if orders >= WINNER_ORDERS and cpa is not None:
            signal = "winner_candidate" if cpa <= be else "over_stop_loss"
        elif orders == 0 and spend >= STOP_LOSS_K * be:
            signal = "over_stop_loss"
    return {
        "break_even_cpa_minor": be,
        "stop_loss_minor": STOP_LOSS_K * be if be is not None and be > 0 else None,
        "signal": signal,
        "signal_reason": NO_BREAK_EVEN if stage == "testing" and be is None else None,
    }


def view(row: ProductTest, title: str, image_url: str | None) -> ProductTestOut:
    spend, orders = row.ad_spend_minor, row.orders
    cpa = round(Fraction(spend, orders)) if orders else None  # round() is half-even
    fields = ProductTestOut.model_fields.keys() - COMPUTED
    return ProductTestOut(
        **{name: getattr(row, name) for name in fields},
        product_title=title,
        product_image_url=image_url,
        cpa_minor=cpa,
        roas=row.revenue_minor / spend if spend else None,
        **stop_loss(row.stage, row.start_snapshot, spend, orders, cpa),
    )


def since_start(session: Session, principal: Principal, row: ProductTest) -> SinceStart | None:
    """The start snapshot against a fresh calc of its scenario: the same supplier, variant,
    quantity, method, DDP, price and owner estimates, with settings and observations read now."""
    snap = row.start_snapshot
    if snap is None:
        return None
    pinned = ("supplier_listing_id", "variant_id", "quantity", "method", "ddp", "price_minor")
    scenario = {key: snap[key] for key in (*pinned, *snap["estimates"]) if snap[key] is not None}
    try:
        fresh = calc_profit(
            ProfitCalcRequest(product_id=row.product_id, **scenario), principal, session
        )
    except APIError as exc:  # the listing, variant or product is gone
        return SinceStart(changes=[], reason=exc.detail, as_of=None)
    new = fresh.model_dump()
    changes = [
        Change(input=key, old=snap[key], new=new[key])
        for key in get_args(Compared)
        if snap[key] != new[key]
    ]
    return SinceStart(changes=changes, reason=None, as_of=fresh.as_of)


def owned(session: Session, principal: Principal, test_id: int) -> ProductTest:
    row = session.get(ProductTest, test_id)
    if row is None or row.workspace_id != principal.workspace_id:
        raise APIError(404, "not_found", "Test not found.")
    return row


def view_one(session: Session, row: ProductTest) -> ProductTestOut:
    card = session.execute(with_card(select(*CARD)).where(ProductTest.id == row.id)).one()
    return view(row, *card)


def apply(
    session: Session, principal: Principal, row: ProductTest, patch: ProductTestPatch
) -> None:
    """Patch the row and run the stage moves' side effects; raise before anything is saved."""
    values = patch.model_dump(exclude_unset=True, exclude={"scenario", "product_id"})
    old, stage = row.stage, values.get("stage", row.stage)
    snapshot = stage == "testing" and row.start_snapshot is None
    if patch.scenario is not None and not snapshot:
        raise APIError(
            422, "snapshot_locked", "A scenario is only taken when the test first enters Testing."
        )
    if snapshot:  # before any change: the calc may commit the workspace's first settings row
        scenario = patch.scenario.model_dump() if patch.scenario else {}
        calc = calc_profit(
            ProfitCalcRequest(product_id=row.product_id, **scenario), principal, session
        )
        now = datetime.now(UTC).isoformat()
        row.start_snapshot = calc.model_dump(mode="json") | {"captured_at": now}
    for key, value in values.items():
        setattr(row, key, value)
    if old == "killed" and stage != "killed" and "kill_reason" not in values:
        row.kill_reason = None
    if old in ENDED and stage not in ENDED and "ended_on" not in values:
        row.ended_on = None
    today = datetime.now(UTC).date()
    if stage == "testing" and row.started_on is None:
        row.started_on = today
    if stage in ENDED and row.ended_on is None:
        row.ended_on = today
    if (stage == "killed") != (row.kill_reason is not None):
        raise APIError(422, "kill_reason", "Killed needs a kill reason, and only Killed has one.")
    if row.started_on and row.ended_on and row.ended_on < row.started_on:
        raise APIError(422, "date_order", "ended_on is before started_on.")


@router.get("", response_model=ProductTestPage)
def list_tests(
    principal: CurrentPrincipal,
    session: DB,
    stage: Stage | None = None,
    cursor: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ProductTestPage:
    mine = ProductTest.workspace_id == principal.workspace_id
    query = with_card(select(ProductTest, *CARD)).where(mine)
    if stage is not None:
        query = query.where(ProductTest.stage == stage)
    if cursor is not None:
        query = query.where(ProductTest.id < cursor)
    rows = session.execute(query.order_by(ProductTest.id.desc()).limit(limit + 1)).tuples().all()
    counts = session.execute(
        select(ProductTest.kill_reason, func.count())
        .where(mine, ProductTest.stage == "killed")
        .group_by(ProductTest.kill_reason)
    ).tuples()
    return ProductTestPage(
        items=[view(*row) for row in rows[:limit]],
        next_cursor=rows[limit - 1][0].id if len(rows) > limit else None,
        kill_reasons=dict(counts.all()),
    )


@router.post("", response_model=ProductTestOut, status_code=201)
def create_test(
    body: ProductTestCreate, principal: CurrentPrincipal, session: DB
) -> ProductTestOut:
    live_product(session, body.product_id)
    row = ProductTest(workspace_id=principal.workspace_id, product_id=body.product_id, stage="idea")
    apply(session, principal, row, body)
    session.add(row)
    session.commit()  # a second open test for the product is a 409 (uq_product_tests_open)
    return view_one(session, row)


@router.get("/{test_id}", response_model=ProductTestDetail)
def get_test(test_id: TestId, principal: CurrentPrincipal, session: DB) -> ProductTestDetail:
    row = owned(session, principal, test_id)
    test = view_one(session, row)  # first: the fresh calc may commit, which expires the row
    return ProductTestDetail(**test.model_dump(), since_start=since_start(session, principal, row))


@router.patch("/{test_id}", response_model=ProductTestOut)
def patch_test(
    test_id: TestId, patch: ProductTestPatch, principal: CurrentPrincipal, session: DB
) -> ProductTestOut:
    row = owned(session, principal, test_id)
    apply(session, principal, row, patch)
    session.commit()
    return view_one(session, row)
