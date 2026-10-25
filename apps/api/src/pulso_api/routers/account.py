from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_core.models import WorkspaceSettings

router = APIRouter(prefix="/v1")
BasisPoints = Annotated[int, Field(ge=0, le=10000, strict=True)]
MinorUnits = Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)]
# The table checks only `>= 0` (US duty can pass 100%); the cap is the Profit override's (DEC-246).
DutyBasisPoints = Annotated[int, Field(ge=0, le=100_000, strict=True)]
DUTY_NOT_SET = "Null: duty not set, so margins that need it stay incomplete (never 0)."


class Me(BaseModel):
    user_id: UUID
    workspace_id: UUID
    is_admin: bool


class SettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    workspace_id: UUID
    default_country: Literal["US"]
    currency: Literal["USD"]
    payment_fee_bps: BasisPoints
    payment_fee_fixed_minor: MinorUnits
    shopify_fee_bps: BasisPoints
    default_cpa_minor: MinorUnits
    target_margin_bps: BasisPoints
    duty_default_bps: DutyBasisPoints | None = Field(description=DUTY_NOT_SET)
    returns_bps: BasisPoints
    customs_fee_minor: MinorUnits


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_country: Literal["US"] | None = None
    currency: Literal["USD"] | None = None
    payment_fee_bps: BasisPoints | None = None
    payment_fee_fixed_minor: MinorUnits | None = None
    shopify_fee_bps: BasisPoints | None = None
    default_cpa_minor: MinorUnits | None = None
    target_margin_bps: BasisPoints | None = None
    duty_default_bps: DutyBasisPoints | None = Field(None, description=DUTY_NOT_SET)
    returns_bps: BasisPoints | None = None
    customs_fee_minor: MinorUnits | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        # Only duty may be cleared: null is "duty not set", which every other field lacks.
        if isinstance(value, dict) and any(
            item is None for key, item in value.items() if key != "duty_default_bps"
        ):
            raise ValueError("Settings fields cannot be null")
        return value


@router.get("/me", response_model=Me)
def get_me(principal: Annotated[Principal, Depends(current_principal)]) -> Me:
    return Me(
        user_id=principal.user_id, workspace_id=principal.workspace_id, is_admin=principal.is_admin
    )


def workspace_settings(session: Session, principal: Principal) -> WorkspaceSettings:
    """The caller's settings row, created with the table defaults if it is missing."""
    settings = session.get(WorkspaceSettings, principal.workspace_id)
    if settings is None:
        session.execute(
            insert(WorkspaceSettings)
            .values(workspace_id=principal.workspace_id)
            .on_conflict_do_nothing(index_elements=[WorkspaceSettings.workspace_id])
        )
        session.commit()
        settings = session.get_one(WorkspaceSettings, principal.workspace_id)
    return settings


@router.get("/settings", response_model=SettingsResponse)
def get_workspace_settings(
    principal: Annotated[Principal, Depends(current_principal)],
    session: Annotated[Session, Depends(get_db)],
) -> SettingsResponse:
    return SettingsResponse.model_validate(workspace_settings(session, principal))


@router.patch("/settings", response_model=SettingsResponse)
def patch_workspace_settings(
    patch: SettingsPatch,
    principal: Annotated[Principal, Depends(current_principal)],
    session: Annotated[Session, Depends(get_db)],
) -> SettingsResponse:
    settings = workspace_settings(session, principal)
    for key, value in patch.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)
    session.commit()
    session.refresh(settings)
    return SettingsResponse.model_validate(settings)
