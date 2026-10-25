"""Worker-only adapter wiring. Importing registrations never enables a source."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from pulso_core.models import Source
from pulso_core.settings import get_settings
from pulso_sources import cj, google_trends, listing_images, shopify_stores
from pulso_sources.fx_frankfurter import FrankfurterAdapter, plan
from pulso_sources.google_trends.live import GoogleTrendsAdapter
from pulso_sources.seed_approval import approved_targets
from pulso_workers.tasks import PLANS, Plan, UnknownJob


def fx_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "fx":
        raise UnknownJob("Unsupported FX job")
    return Plan(
        FrankfurterAdapter(),
        plan(session, datetime.now(UTC).date()),
        get_settings().fx_wall_time_seconds,
    )


def shopify_plan(session: Session, source: Source, job: str) -> Plan:
    if job not in {"catalog", "variants_js"}:
        raise UnknownJob("Unsupported Shopify job")
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
        raise UnknownJob("Unsupported Trends job")
    adapter = GoogleTrendsAdapter()
    return Plan(
        adapter,
        google_trends.plan(session),
        get_settings().trends_wall_time_seconds,
        request_hook=adapter.request_hook,
        collector_max_retries=1,  # DEC-157: an outage spends at most two reservations.
        finalize=adapter.finalize,
    )


def images_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "images":
        raise UnknownJob("Unsupported listing images job")
    settings = get_settings()
    adapter, targets = listing_images.plan(session, settings=settings)
    return Plan(adapter, targets, settings.collector_wall_time_seconds)


def cj_plan(session: Session, source: Source, job: str) -> Plan:
    if job != "catalog":  # freight waits for a tracked-product selection (DEC-321b)
        raise UnknownJob("Unsupported CJ job")
    names = [row["name"] for row in approved_targets(session, source.key)]
    if not names:
        raise ValueError("No approved CJ categories")
    adapter = cj.CatalogAdapter(names)
    targets = adapter.targets()
    return Plan(
        adapter,
        targets,
        get_settings().cj_wall_time_seconds,
        collect=lambda db, run_id, settings, stop: cj.collect(
            db, run_id, targets, settings=settings, adapter=adapter, stop_exceptions=stop
        ),
    )


PLANS["fx_frankfurter"] = fx_plan
PLANS["shopify_stores"] = shopify_plan
PLANS["google_trends"] = trends_plan
PLANS["listing_images"] = images_plan
PLANS["cj"] = cj_plan
