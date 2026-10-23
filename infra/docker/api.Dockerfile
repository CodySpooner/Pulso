# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=0 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY apps ./apps
COPY packages ./packages
COPY alembic.ini ./
# No cache mount: Railway rejects ids without its per-service key (DEC-102).
RUN uv sync --locked --no-dev --no-editable --package pulso-api

FROM python:3.14-slim-trixie AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PULSO_SCHEDULER=off COLLECTORS_LIVE=off API_PORT=8000
RUN useradd --create-home --uid 10001 pulso
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/alembic.ini ./
# Alembic's config and revision files are also needed by the pre-deploy command.
COPY --from=build /app/packages/core ./packages/core
USER pulso
EXPOSE 8000
CMD ["python", "-m", "pulso_api"]
