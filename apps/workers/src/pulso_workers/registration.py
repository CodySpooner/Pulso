"""Worker-only adapter wiring. Importing registrations never enables a source."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_core.settings import get_settings
from pulso_sources import shopify_stores
from pulso_sources.fx_frankfurter import FrankfurterAdapter, plan
from pulso_workers.tasks import PLANS, Plan


def fx_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "fx":
        raise ValueError("Unsupported FX job")
    return Plan(
        FrankfurterAdapter(),
        plan(session, datetime.now(UTC).date()),
        get_settings().fx_wall_time_seconds,
    )


def shopify_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "catalog":
        raise ValueError("Unsupported Shopify job")
    settings = get_settings()
    adapter, targets, finalize = shopify_stores.plan(session, source, settings=settings)
    return Plan(
        adapter,
        targets,
        settings.shopify_wall_time_seconds,
        request_hook=adapter.request_hook,
        collector_max_retries=0,
        finalize=finalize,
    )


PLANS["fx_frankfurter"] = fx_plan
PLANS["shopify_stores"] = shopify_plan
