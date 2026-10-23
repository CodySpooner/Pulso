"""Sequential, guarded Shopify catalogs; call collect under the worker's source lock."""

import time
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from urllib.request import Request as URLRequest
from urllib.robotparser import RobotFileParser

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Listing,
    ListingSnapshot,
    RawPayload,
    Source,
    SourceEvent,
    Store,
    WorkspaceTrackedStore,
)
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.framework import Request, Response, RunDeferred, Target, execute_run
from pulso_sources.seed_approval import approved_targets
from pulso_sources.shopify_stores.records import Catalog, Meta, parse, upsert
from pulso_sources.shopify_stores.variants import JSProduct

STORE_SPACING_SECONDS = 10
_next_global = 0.0
_next_store: dict[str, float] = {}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


class RobotsDisallowed(ValueError):
    pass


class ShopifyAdapter:
    parser_version = "shopify-2"
    parse = staticmethod(parse)
    upsert = staticmethod(upsert)

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.responses: dict[str, Response] = {}
        self.delays: dict[str, float] = {}
        self.seen: dict[str, set[str]] = {}
        self.cache: dict[str, tuple[RawPayload, bytes]] = {}
        self.deadline = time.monotonic() + settings.shopify_wall_time_seconds

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        global _next_global
        url, domain = str(request.params["url"]), str(request.params["domain"])
        if url in self.responses:
            raise RunDeferred("same_url_in_run")
        delay = max(
            0, _next_global - time.monotonic(), _next_store.get(domain, 0) - time.monotonic()
        )
        if time.monotonic() + delay >= self.deadline:
            raise RunDeferred("wall_time_budget")
        if delay:
            time.sleep(delay)
        _next_global = time.monotonic() + 60 / self.settings.shopify_requests_per_minute
        _next_store[domain] = time.monotonic() + max(
            STORE_SPACING_SECONDS, self.delays.get(domain, 0)
        )
        self.responses[url] = Response(None, complete=False)  # Also reserves transport failures.
        headers = {"User-Agent": user_agent}
        if request.params.get("etag"):
            headers["If-None-Match"] = str(request.params["etag"])
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            try:
                response = opener.open(
                    URLRequest(url, headers=headers),
                    timeout=self.settings.collector_request_timeout_seconds,
                )
            except HTTPError as error:
                response = error
            with response:
                body = response.read()
                result = Response(
                    None if response.code == 304 else body,
                    response.code,
                    response.headers.get("Content-Type"),
                    response.headers.get("ETag"),
                    headers=dict(response.headers.items()),
                )
        except URLError as error:
            raise ConnectionError("store_transport") from error
        self.responses[url] = result
        return result

    def request_hook(
        self,
        session: Session,
        source: Source,
        run: CollectorRun,
        request: Request,
        response: Response | None,
    ) -> None:
        if response is None:
            return
        store = session.get_one(Store, request.params["store_id"])
        if response.status_code == 403:
            store.status = "blocked"
        elif request.params["path"] != "/robots.txt" and (
            response.status_code in {402, 404}
            or any(
                k.lower() == "location" and "/password" in v.lower()
                for k, v in response.headers.items()
            )
            or (response.status_code == 200 and (response.body or b"").lstrip().startswith(b"<"))
        ):
            store.status = "untrackable"
        if response.status_code == 430 and source.enabled:
            source.enabled, source.status = False, "blocked"
            source.disabled_at, source.disabled_reason = datetime.now(UTC), "http_430"
            session.add(SourceEvent(source_id=source.id, action="disable", reason="http_430"))

    def catalog(self, store: Store, panel: Sequence[Listing] | None = None) -> Iterator[Request]:
        origin = f"https://{store.domain}"

        def request(path: str) -> Request:
            url = origin + path
            cached = self.cache.get(url)
            conditional = (
                cached
                and (path.startswith("/products.json?") or path.endswith(".js"))
                and (cached[0].request.get("currency") == store.currency)
            )
            return Request(
                params={
                    "url": url,
                    "domain": store.domain,
                    "store_id": store.id,
                    "path": path,
                    "currency": store.currency,
                    "etag": cached[0].etag if conditional and cached else None,
                }
            )

        robots_url = origin + "/robots.txt"
        cached = self.cache.get(robots_url)
        if cached and cached[0].captured_at.replace(tzinfo=UTC) > datetime.now(UTC) - timedelta(
            hours=24
        ):
            body = cached[1]
        else:
            yield request("/robots.txt")
            if self.responses[robots_url].status_code != 200:
                raise ValueError("robots_unavailable")
            body = self.responses[robots_url].body or b""
        robots = RobotFileParser()
        robots.parse(body.decode("utf-8-sig").splitlines())
        rate = robots.request_rate("PulsoBot")
        self.delays[store.domain] = max(
            float(robots.crawl_delay("PulsoBot") or 0), rate.seconds / rate.requests if rate else 0
        )
        _next_store[store.domain] = max(
            _next_store.get(store.domain, 0), time.monotonic() + self.delays[store.domain]
        )
        if not robots.can_fetch("PulsoBot", origin + "/meta.json"):
            raise RobotsDisallowed()
        yield request("/meta.json")
        Meta.model_validate_json(self.responses[origin + "/meta.json"].body or b"")
        if panel is not None:
            for listing in panel:
                path = f"/products/{listing.handle}.js"
                if not robots.can_fetch("PulsoBot", origin + path):
                    raise RobotsDisallowed()
                item = Request(params={**request(path).params, "listing_id": listing.id})
                yield item
                response = self.responses[origin + path]
                if response.status_code == 304:
                    if not item.params["etag"]:
                        raise ValueError("unproven_304")
                    product = JSProduct.model_validate_json(self.cache[origin + path][1])
                    if listing.external_id != f"{store.shop_id}:{product.id}":
                        raise ValueError("Product identity changed")
            return
        seen = self.seen[store.domain] = set()
        page = 1
        while True:
            path = f"/products.json?limit=250&page={page}"
            if not robots.can_fetch("PulsoBot", origin + path):
                raise RobotsDisallowed()
            item = request(path)
            yield item
            response = self.responses[origin + path]
            cached = self.cache.get(origin + path)
            if response.status_code == 304:
                if cached is None or not item.params["etag"]:
                    raise ValueError("unproven_304")
                body = cached[1]
            else:
                body = response.body or b""
            products = Catalog.model_validate_json(body).products
            if any(str(p.id) in seen for p in products):
                raise ValueError("invalid_catalog_page")
            seen.update(str(p.id) for p in products)
            if len(products) < 250:
                return
            page += 1


def plan(
    session: Session, source: Source, *, settings: Settings, job: str = "catalog"
) -> tuple[ShopifyAdapter, list[Target], Callable[[Session, CollectorRun], None]]:
    """Preload under the source lock; only catalog plans finalize store completeness."""
    global _next_global
    session.expire_on_commit = False
    if source.key != "shopify_stores":
        raise ValueError("Wrong source")
    if job not in {"catalog", "variants_js"}:
        raise ValueError("Unsupported Shopify job")
    domains = {row["domain"] for row in approved_targets(session, source.key)}
    stores = list(
        session.scalars(
            select(Store).where(
                Store.domain.in_(domains), Store.id.in_(select(WorkspaceTrackedStore.store_id))
            )
        )
    )
    adapter = ShopifyAdapter(settings)
    capture_domain = RawPayload.request["domain"].as_string()
    last_captures = session.execute(
        select(capture_domain, func.max(RawPayload.captured_at))
        .where(RawPayload.source_id == source.id)
        .group_by(capture_domain)
    ).all()
    now, monotonic = datetime.now(UTC), time.monotonic()
    for domain, captured_at in last_captures:
        # Restore spacing after a restart without shortening this process's deadlines.
        captured = monotonic + (captured_at.replace(tzinfo=UTC) - now).total_seconds()
        _next_global = max(_next_global, captured + 60 / settings.shopify_requests_per_minute)
        if domain is not None:
            _next_store[domain] = max(_next_store.get(domain, 0), captured + STORE_SPACING_SECONDS)
    # A failed tail invalidates cache eligibility for every page of that store's run.
    eligible = (
        select(
            RawPayload.id,
            func.row_number()
            .over(partition_by=RawPayload.request["url"].as_string(), order_by=RawPayload.id.desc())
            .label("rank"),
        )
        .join(CollectorRunTarget, CollectorRunTarget.run_id == RawPayload.run_id)
        .where(
            RawPayload.source_id == source.id,
            RawPayload.request["domain"].as_string().in_(domains),
            RawPayload.status_code == 200,
            CollectorRunTarget.scope.in_(["shopify_catalog", "shopify_variants_js"]),
            CollectorRunTarget.status == "success",
            CollectorRunTarget.target_id == RawPayload.request["domain"].as_string(),
        )
        .subquery()
    )
    captures = list(
        session.scalars(
            select(RawPayload)
            .join(eligible, eligible.c.id == RawPayload.id)
            .where(eligible.c.rank == 1)
        )
    )
    session.commit()
    for payload in captures:
        adapter.cache[payload.request["url"]] = (payload, storage.read_capture(payload))
    targets = []
    for store in stores:
        if store.domain == "inspireuplift.com" and store.status == "active":
            store.status = "blocked"  # Recorded seed pre-check 403; never probe it again.
        if store.status != "active":
            targets.append(Target("shopify_excluded", f"{store.domain}:{store.status}", ()))
        else:
            panel = None
            if job == "variants_js":
                latest = (
                    select(ListingSnapshot.source_updated_at)
                    .where(ListingSnapshot.listing_id == Listing.id)
                    .order_by(ListingSnapshot.captured_at.desc(), ListingSnapshot.id.desc())
                    .limit(1)
                    .scalar_subquery()
                )
                panel = list(
                    session.scalars(
                        select(Listing)
                        .where(
                            Listing.store_id == store.id,
                            Listing.source_id == source.id,
                            Listing.delisted_at.is_(None),
                            Listing.handle.is_not(None),
                        )
                        .order_by(latest.desc().nulls_last(), Listing.id)
                        .limit(settings.shopify_js_panel_size)
                    )
                )
                if not panel:
                    continue
            targets.append(Target(f"shopify_{job}", store.domain, adapter.catalog(store, panel)))
    session.commit()

    def finalize(session: Session, run: CollectorRun) -> None:
        if job != "catalog":
            return
        for store in stores:
            target = session.get(CollectorRunTarget, (run.id, "shopify_catalog", store.domain))
            if target is None or target.status != "success":
                continue
            seen = [f"{store.shop_id}:{pid}" for pid in adapter.seen[store.domain]]
            scope = (Listing.store_id == store.id, Listing.source_id == source.id)
            session.execute(
                update(Listing)
                .where(*scope, Listing.external_id.in_(seen))
                .values(last_seen_at=target.captured_at, delisted_at=None)
            )
            session.execute(
                update(Listing)
                .where(*scope, Listing.external_id.not_in(seen), Listing.delisted_at.is_(None))
                .values(delisted_at=target.captured_at)
            )
            store.last_crawled_at = target.captured_at
        session.commit()

    return adapter, targets, finalize


def collect(session: Session, run_id: int, *, settings: Settings) -> CollectorRun:
    """Own the lifecycle transaction; source enablement remains external and off by default."""
    session.expire_on_commit = False
    run = session.get_one(CollectorRun, run_id)
    if run.status != "queued":
        return run
    adapter, targets, finalize = plan(
        session, session.get_one(Source, run.source_id), settings=settings
    )
    run = execute_run(
        session,
        run_id,
        adapter,
        targets,
        settings=settings.model_copy(update={"collector_max_retries": 0}),
        wall_time_seconds=settings.shopify_wall_time_seconds,
        request_hook=adapter.request_hook,
    )
    finalize(session, run)
    return run
