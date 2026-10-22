from http import HTTPStatus
from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str
    request_id: str
    errors: list[dict[str, Any]] = Field(default_factory=list)


class APIError(Exception):
    def __init__(self, status: int, code: str, detail: str) -> None:
        self.status = status
        self.code = code
        self.detail = detail


def problem_response(
    request: Request,
    status: int,
    code: str,
    detail: str,
    errors: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    problem = Problem(
        title=HTTPStatus(status).phrase,
        status=status,
        code=code,
        detail=detail,
        request_id=request.state.request_id,
        errors=errors or [],
    )
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else {}
    return JSONResponse(
        problem.model_dump(),
        status_code=status,
        media_type="application/problem+json",
        headers=headers,
    )


PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"content": {"application/problem+json": {"schema": Problem.model_json_schema()}}}
    for status in (401, 403, 404, 409, 422, 500, 503)
}
