# syntax=docker/dockerfile:1
FROM python:3.14-slim-trixie AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.23 /uv /bin/uv
ENV UV_PYTHON_DOWNLOADS=0 UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY apps ./apps
COPY packages ./packages
# No cache mount: Railway rejects ids without its per-service key (DEC-102).
RUN uv sync --locked --no-dev --no-editable --package pulso-workers

FROM python:3.14-slim-trixie AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PULSO_SCHEDULER=off COLLECTORS_LIVE=off
# Phase 2 adds CPU torch/CLIP weights; Phase 6 adds libgomp1 with LightGBM.
RUN useradd --create-home --uid 10001 pulso && mkdir /app && chown pulso:pulso /app
WORKDIR /app
COPY --from=build /app/.venv ./.venv
USER pulso
CMD ["celery", "-A", "pulso_workers.celery_app:app", "worker", "-Q", "collect,default", "--loglevel=INFO"]
