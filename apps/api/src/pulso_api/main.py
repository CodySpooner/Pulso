import logging
import os
import re
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import DataError, IntegrityError
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from pulso_api.errors import PROBLEM_RESPONSES, APIError, problem_response
from pulso_api.publisher import get_publisher
from pulso_api.routers import (
    account,
    admin,
    alerts,
    amazon,
    boards,
    health,
    matching,
    popular_products,
    product_aliexpress,
    product_keywords,
    product_sellers,
    product_series,
    product_suppliers,
    products,
    profit,
    search,
    testing,
    watchlists,
)
from pulso_core.logging import configure_logging, request_id

logger = logging.getLogger("pulso.api")


def create_app() -> FastAPI:
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    app = FastAPI(
        title="Pulso API",
        version="0.1.0",
        generate_unique_id_function=lambda route: route.name,
        responses=PROBLEM_RESPONSES,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("x-request-id", "")
        correlation = supplied if re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", supplied) else str(uuid4())
        request.state.request_id = correlation
        token = request_id.set(correlation)
        started = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.exception("request_failed", extra={"error_type": type(exc).__name__})
                response = problem_response(
                    request,
                    500,
                    "internal_error",
                    "An internal error occurred.",
                )
            response.headers["X-Request-ID"] = correlation
            response.headers["Cache-Control"] = "no-store"
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            return response
        finally:
            request_id.reset(token)

    @app.exception_handler(APIError)
    async def api_error(request: Request, exc: APIError) -> Response:
        return problem_response(request, exc.status, exc.code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        errors = [{key: value[key] for key in ("loc", "msg", "type")} for value in exc.errors()]
        return problem_response(request, 422, "validation_error", "Invalid request.", errors)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> Response:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return problem_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(IntegrityError)
    async def conflict(request: Request, exc: IntegrityError) -> Response:
        return problem_response(
            request, 409, "conflict", "The request conflicts with existing data."
        )

    @app.exception_handler(DataError)
    async def nul_text(request: Request, exc: DataError) -> Response:
        # Path, query or cursor text that reached SQL with a NUL (DEC-287); others stay 500s.
        if "cannot contain NUL" not in str(exc.orig):
            raise exc
        return problem_response(
            request, 422, "invalid_text", "Text cannot contain a NUL character."
        )

    app.include_router(health.router)
    app.include_router(account.router)
    app.include_router(admin.router)
    app.include_router(alerts.rules_router)
    app.include_router(amazon.router)
    app.include_router(amazon.products_router)
    app.include_router(boards.router)
    app.include_router(matching.router)
    app.include_router(popular_products.router)
    app.include_router(products.router)
    app.include_router(products.categories_router)
    app.include_router(profit.router)
    app.include_router(product_aliexpress.router)
    app.include_router(product_keywords.router)
    app.include_router(product_sellers.router)
    app.include_router(product_series.router)
    app.include_router(product_suppliers.router)
    app.include_router(search.router)
    app.include_router(testing.router)
    app.include_router(watchlists.router)
    app.include_router(watchlists.products_router)
    app.dependency_overrides[admin.get_publisher] = get_publisher
    return app


app = create_app()
