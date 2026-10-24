import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWTError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_api.dependencies import get_db
from pulso_api.errors import APIError
from pulso_core.models import User, Workspace, WorkspaceMember, WorkspaceSettings
from pulso_core.settings import Settings, get_settings


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    workspace_id: UUID
    is_admin: bool = True


@lru_cache
def jwks_client(url: str) -> PyJWKClient:
    # Cache the set with a TTL; indefinite per-key caching would outlive revocation.
    return PyJWKClient(url, lifespan=300, timeout=3)


def verify_token(token: str, settings: Settings) -> str:
    if not settings.clerk_issuer or not settings.clerk_jwks_url:
        raise APIError(503, "auth_unconfigured", "Authentication is not configured.")
    try:
        key = jwks_client(settings.clerk_jwks_url).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            leeway=5,
            options={"require": ["iss", "exp", "nbf", "iat", "sub", "azp"]},
        )
    # PyJWT wraps only network errors; a JWKS body that isn't JSON escapes its fetch unwrapped.
    except (PyJWKClientConnectionError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise APIError(
            503, "auth_unavailable", "Authentication is temporarily unavailable."
        ) from exc
    except PyJWTError as exc:
        raise APIError(401, "bad_token", "Invalid session token.") from exc
    if claims["azp"] not in settings.clerk_authorized_parties:
        raise APIError(401, "bad_azp", "Invalid authorized party.")
    subject = claims["sub"]
    if not isinstance(subject, str) or not subject:
        raise APIError(401, "bad_token", "Invalid session token.")
    if subject not in settings.platform_admin_user_ids:
        raise APIError(403, "not_allowlisted", "This Pulso is private.")
    return subject


def provision_principal(session: Session, subject: str) -> Principal:
    with session.begin():
        # The unique user insert serializes concurrent first logins in one transaction.
        user_id = session.scalar(
            insert(User)
            .values(clerk_user_id=subject)
            .on_conflict_do_nothing(index_elements=[User.clerk_user_id])
            .returning(User.id)
        )
        if user_id is not None:
            workspace = Workspace(name="My workspace")
            session.add(workspace)
            session.flush()
            session.add_all(
                [
                    WorkspaceMember(workspace_id=workspace.id, user_id=user_id),
                    WorkspaceSettings(workspace_id=workspace.id),
                ]
            )
            return Principal(user_id, workspace.id)
        row = session.execute(
            select(User.id, WorkspaceMember.workspace_id)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(User.clerk_user_id == subject)
            .order_by(WorkspaceMember.workspace_id)
            .limit(1)
        ).one()
        return Principal(row[0], row[1])


def current_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(HTTPBearer(auto_error=False))
    ],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_db)],
    session_token: Annotated[str | None, Cookie(alias="__session")] = None,
) -> Principal:
    token = credentials.credentials if credentials else session_token
    if not token:
        raise APIError(401, "missing_token", "A session token is required.")
    return provision_principal(session, verify_token(token, settings))
