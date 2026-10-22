from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from pulso_api.auth import Principal, current_principal
from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_core.models import WorkspaceSettings

router = APIRouter(prefix="/v1")
BasisPoints = Annotated[int, Field(ge=0, le=10000, strict=True)]
MinorUnits = Annotated[int, Field(ge=0, le=2**63 - 1, strict=True)]


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


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_country: Literal["US"] | None = None
    currency: Literal["USD"] | None = None
    payment_fee_bps: BasisPoints | None = None
    payment_fee_fixed_minor: MinorUnits | None = None
    shopify_fee_bps: BasisPoints | None = None
    default_cpa_minor: MinorUnits | None = None
    target_margin_bps: BasisPoints | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null(cls, value: Any) -> Any:
        if isinstance(value, dict) and any(item is None for item in value.values()):
            raise ValueError("Settings fields cannot be null")
        return value


@router.get("/me", response_model=Me)
def get_me(principal: Annotated[Principal, Depends(current_principal)]) -> Me:
    return Me(
        user_id=principal.user_id, workspace_id=principal.workspace_id, is_admin=principal.is_admin
    )


def workspace_settings(session: Session, principal: Principal) -> WorkspaceSettings:
    settings = session.get(WorkspaceSettings, principal.workspace_id)
    if settings is None:
        raise APIError(404, "not_found", "Workspace settings not found.")
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
