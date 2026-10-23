"""Worker-only adapter wiring. Importing registrations never enables a source."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_core.settings import get_settings
from pulso_sources import google_trends, shopify_stores
from pulso_sources.fx_frankfurter import FrankfurterAdapter, plan
from pulso_sources.google_trends.live import GoogleTrendsAdapter
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
    if job not in {"catalog", "variants_js"}:
        raise ValueError("Unsupported Shopify job")
    settings = get_settings()
    adapter, targets, finalize = shopify_stores.plan(session, source, settings=settings, job=job)
    return Plan(
        adapter,
        targets,
        settings.shopify_wall_time_seconds,
        request_hook=adapter.request_hook,
        collector_max_retries=0,
        finalize=finalize,
    )


def trends_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "trends":
        raise ValueError("Unsupported Trends job")
    adapter = GoogleTrendsAdapter()
    return Plan(
        adapter,
        google_trends.plan(session),
        get_settings().trends_wall_time_seconds,
        request_hook=adapter.request_hook,
        collector_max_retries=1,  # DEC-157: an outage spends at most two reservations.
        finalize=adapter.finalize,
    )


PLANS["fx_frankfurter"] = fx_plan
PLANS["shopify_stores"] = shopify_plan
PLANS["google_trends"] = trends_plan
