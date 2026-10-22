from collections.abc import Callable
from contextlib import closing
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import text
from starlette.responses import JSONResponse

from pulso_api.errors import problem_response
from pulso_core.db import get_engine
from pulso_core.s3 import make_client
from pulso_core.settings import Settings, get_settings

router = APIRouter()


class Health(BaseModel):
    status: Literal["ok"] = "ok"


def check_postgres(settings: Settings) -> None:
    with get_engine(statement_timeout=10_000).connect() as connection:
        connection.execute(text("SELECT 1"))


def check_redis(settings: Settings) -> None:
    with Redis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=1,
        socket_timeout=1,
    ) as client:
        client.ping()


def check_s3(settings: Settings) -> None:
    with closing(make_client(settings)) as client:
        client.head_bucket(Bucket=settings.s3_bucket_raw)


@router.get("/healthz", response_model=Health)
def healthz() -> Health:
    return Health()


@router.get("/readyz", response_model=Health)
def readyz(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Health | JSONResponse:
    failures = []
    checks: dict[str, Callable[[Settings], None]] = {
        "postgres": check_postgres,
        "redis": check_redis,
        "s3": check_s3,
    }
    for name, check in checks.items():
        try:
            check(settings)
        except Exception:
            # Dependency exceptions may contain credentials or endpoint URLs.
            failures.append(name)
    if failures:
        return problem_response(
            request,
            503,
            "dependency_unavailable",
            "Unavailable dependencies: " + ", ".join(failures),
        )
    return Health()
