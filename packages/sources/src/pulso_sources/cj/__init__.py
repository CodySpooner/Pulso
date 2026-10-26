"""CJ catalog collection; source enablement remains an external owner gate."""

import hashlib
import json
import logging
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import BaseModel, Field, NonNegativeInt, StrictInt
from sqlalchemy import select
from sqlalchemy.orm import Session

from pulso_core.landed_cost_loader import PRICE_CAPTURE
from pulso_core.models import (
    CollectorRun,
    Listing,
    ListingSnapshot,
    RawPayload,
    Source,
    SourceEvent,
    Supplier,
)
from pulso_core.money import to_minor
from pulso_core.settings import Settings
from pulso_sources import storage
from pulso_sources.cj.budget import POINTS, record_points, reserve
from pulso_sources.cj.categories import resolve
from pulso_sources.cj.errors import CJError, classify_error
from pulso_sources.cj.transport import Transport
from pulso_sources.framework import (
    Adapter,
    CollectorsLiveDisabled,
    Request,
    Response,
    Target,
    UpsertStats,
    Writer,
    append_observation,
    execute_run,
)
from pulso_sources.framework.lifecycle import BLOCK_STATUSES, _retry_after

if TYPE_CHECKING:
    from pulso_sources.cj.tracked import TrackedAdapter

logger = logging.getLogger("pulso.sources.cj")  # under configure_logging's "pulso" tree
Identifier = Annotated[str, Field(min_length=1, max_length=200)]
# DEC-120/348: catalog, detail and CSV listing rows own the price; the stock capture's own stock.
PRICE_WRITER = Writer(PRICE_CAPTURE, ("price_min_minor", "price_max_minor", "listed_count"))


class Product(BaseModel):
    id: Identifier
    nameEn: Annotated[str, Field(min_length=1)]
    sellPrice: str
    listedNum: Annotated[StrictInt, Field(ge=0)] | None = None


class Group(BaseModel):
    productList: list[Product]


class Page(BaseModel):
    pageSize: Annotated[int, Field(ge=1, le=100)]
    pageNumber: Annotated[int, Field(ge=1, le=1000)]
    totalRecords: NonNegativeInt
    totalPages: NonNegativeInt
    content: list[Group]


class Record(BaseModel):
    external_id: str
    title: str
    price_min_minor: int
    price_max_minor: int
    listed_count: int | None
    currency: str = "USD"
    observed_for: date | None = None


def parse(body: bytes) -> list[Record]:
    if error := classify_error(Response(body, 200)):
        raise error
    page = Page.model_validate(json.loads(body, parse_float=Decimal)["data"])
    records = []
    seen: set[str] = set()
    for group in page.content:
        for product in group.productList:
            amounts = product.sellPrice.split("-")
            if len(amounts) not in {1, 2}:
                raise ValueError("Invalid CJ price range")
            try:
                low, high = to_minor(amounts[0], "USD"), to_minor(amounts[-1], "USD")
            except InvalidOperation:
                raise ValueError("Invalid CJ price range") from None
            if low < 0 or high < low or product.id in seen:
                raise ValueError("Invalid CJ price range or duplicate product")
            seen.add(product.id)
            records.append(
                Record(
                    external_id=product.id,
                    title=product.nameEn,
                    price_min_minor=low,
                    price_max_minor=high,
                    listed_count=product.listedNum,
                )
            )
    return records


def plan(category_ids: Sequence[str]) -> list[Target]:
    """Bounded panels, not complete category catalogs; IDs must already be resolved."""
    if len(set(category_ids)) != len(category_ids) or any(not c.strip() for c in category_ids):
        raise ValueError("CJ categories require distinct nonempty IDs")
    return [
        Target(
            "cj_catalog_panel",
            f"{category}:{order}:{country or 'all'}",
            [
                Request(
                    params={
                        "endpoint": "/product/listV2",
                        "categoryId": category,
                        "page": page,
                        "size": 100,
                        "orderBy": order,
                        "sort": "desc",
                        **({"countryCode": country} if country else {}),
                    }
                )
                for page in range(1, pages + 1)
            ],
        )
        for category in category_ids
        for order, country, pages in [(1, None, 10), (3, None, 2), (1, "US", 3)]
    ]


def dry_run(category_count: int, *, tracked_products: int = 300, freight_quotes: int = 300) -> int:
    if category_count < 0 or not 0 <= tracked_products <= 300 or not 0 <= freight_quotes <= 300:
        raise ValueError("Invalid CJ plan size")
    points = category_count * 15 * 50 + tracked_products * 2 * 10 + freight_quotes * 10
    if points >= 20000:
        raise ValueError("CJ plan must remain below 20,000 points")
    logger.info("cj_points_projection", extra={"source": "cj", "projected_points": points})
    return points


def category_plan(body: bytes, names: Sequence[str]) -> list[Target]:
    def requests() -> Iterator[Request]:
        # Resolve inside the lifecycle so missing seed evidence is visible in Data Health.
        ids = sorted({cid for group in resolve(body, names).values() for cid in group})
        dry_run(len(ids))
        for panel in plan(ids):
            yield from panel.requests

    return [Target("cj_category_resolution", "catalog", requests())]


class CJAdapter:
    parser_version = "cj-catalog-v1"
    parse = staticmethod(parse)

    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        if self.transport is None:
            raise CollectorsLiveDisabled("CJ collection requires a guarded transport")
        return self.transport.fetch(request)

    def upsert(
        self,
        session: Session,
        records: Sequence[Record],
        payload: RawPayload,
        *,
        parser_version: str,
    ) -> UpsertStats:
        if not records:
            return UpsertStats()
        supplier = session.scalar(select(Supplier).filter_by(platform="cj", external_id="cj"))
        if supplier is None:
            supplier = Supplier(platform="cj", external_id="cj", name="CJ Dropshipping")
            session.add(supplier)
            session.flush()
        inserted = 0
        for record in records:
            listing = session.scalar(
                select(Listing).filter_by(
                    source_id=payload.source_id, external_id=record.external_id
                )
            )
            if listing is None:
                listing = Listing(
                    source_id=payload.source_id,
                    external_id=record.external_id,
                    title=record.title,
                    supplier_id=supplier.id,
                    url="https://cjdropshipping.com/",
                    first_seen_at=payload.captured_at,
                    last_seen_at=payload.captured_at,
                )
                session.add(listing)
                session.flush()
            elif payload.captured_at >= listing.last_seen_at:
                listing.title, listing.last_seen_at = record.title, payload.captured_at
            values = record.model_dump(
                include={"price_min_minor", "price_max_minor", "listed_count", "currency"}
            )
            inserted += append_observation(
                session,
                ListingSnapshot(
                    listing_id=listing.id,
                    raw_payload_id=payload.id,
                    captured_at=payload.captured_at,
                    observed_for=record.observed_for or payload.captured_at.date(),
                    parser_version=parser_version,
                    values_hash=hashlib.sha256(
                        json.dumps(values, sort_keys=True).encode()
                    ).hexdigest(),
                    **values,
                ),
                writer=PRICE_WRITER,
            )
        return UpsertStats(inserted=inserted, unchanged=len(records) - inserted)


class CatalogAdapter(CJAdapter):
    """Scheduled catalog: a captured getCategory first, then the approved names' panels."""

    def __init__(self, names: Sequence[str]) -> None:
        super().__init__()
        self.names, self.tree = list(names), b""

    def parse(self, body: bytes) -> list[Record]:
        data = json.loads(body)
        if isinstance(data, dict) and isinstance(data.get("data"), list):  # listV2 is a page
            self.tree = body
            return []
        return parse(body)

    def targets(self) -> list[Target]:
        def requests() -> Iterator[Request]:
            # The tree goes through the run's hook, so block, disable and raw capture apply.
            # Its free 200 says nothing about the paid listV2 calls (DEC-321a, XR-59).
            yield Request(params={"endpoint": "/product/getCategory"}, resets_blocks=False)
            yield from category_plan(self.tree, self.names)[0].requests

        return [Target("cj_category_resolution", "catalog", requests())]


def collect(
    session: Session,
    run_id: int,
    targets: Sequence[Target],
    *,
    settings: Settings,
    adapter: CJAdapter | TrackedAdapter | None = None,
    stop_exceptions: tuple[type[BaseException], ...] = (),
) -> CollectorRun:
    """Call under the scheduler's source lock; own commits before actual HTTP attempts."""
    run = session.get_one(CollectorRun, run_id)
    source = session.get_one(Source, run.source_id)
    if source.key != "cj":
        raise ValueError("CJ collector requires the CJ source")
    error: CJError | None = None
    attempted = False
    before_count = run.http_requests
    previous_blocks = source.consecutive_block_count
    body_block = False
    failure_response: Response | None = None

    def before_send(endpoint: str) -> None:
        if endpoint in POINTS:
            reserve(session, source, run, endpoint, settings=settings, now=datetime.now(UTC))
        run.http_requests = before_count + transport.sent + 1
        session.commit()

    def rejected(request: Request, response: Response) -> None:
        storage.store_capture(
            session,
            source_id=source.id,
            source_key=source.key,
            run_id=run.id,
            body=response.body,
            content_type=response.content_type,
            status_code=response.status_code,
            etag=response.etag,
            request=request.params,
            captured_at=datetime.now(UTC),
        )
        session.commit()

    def received(response: Response) -> None:
        # Re-read under the row lock so a config write committed mid-request survives.
        session.refresh(source, with_for_update=True)
        record_points(source, response.body, datetime.now(UTC))
        session.commit()

    transport = Transport(settings, before_send, rejected, received)
    adapter = adapter or CJAdapter()
    adapter.transport = transport
    run_adapter: Adapter[Any] = adapter

    def hook(
        db: Session,
        source: Source,
        run: CollectorRun,
        request: Request,
        response: Response | None,
    ) -> None:
        nonlocal error, attempted, before_count, previous_blocks, body_block
        nonlocal failure_response
        try:
            if response is None:
                if attempted:
                    run.http_requests = before_count + transport.sent
                transport.guard(request)
                attempted, before_count = True, run.http_requests
                transport.sent = 0
                previous_blocks = source.consecutive_block_count
            elif failure := classify_error(response):
                failure_response = response
                body_block = response.status_code not in {403, 429, 430} and failure.code in {
                    "cj_points_exhausted",
                    "cj_rate_limited",
                }
                raise failure
        except CJError as failure:
            error = failure
            raise

    try:
        result = execute_run(
            session,
            run_id,
            run_adapter,
            targets,
            settings=settings,
            wall_time_seconds=settings.cj_wall_time_seconds,
            request_hook=hook,
            stop_exceptions=stop_exceptions,
        )
    finally:
        if transport.auth.cache is not None:
            transport.auth.cache.close()
    if attempted:
        result.http_requests = before_count + transport.sent
    error = error or transport.error
    if auth_failure := transport.auth_failure:
        result.last_status_code = source.last_status_code = auth_failure.status_code
        body_block = auth_failure.status_code in BLOCK_STATUSES or (
            error is not None and error.code in {"cj_points_exhausted", "cj_rate_limited"}
        )
        source.consecutive_block_count = previous_blocks if body_block else 0
    if failure_response := transport.auth_failure or failure_response:
        if retry_at := _retry_after(failure_response, datetime.now(UTC)):
            source.retry_not_before = max(source.retry_not_before or retry_at, retry_at)
    if error is not None:
        # P1-30 preserves the generic HTTP block stop; record CJ's more specific code afterward.
        result.error_code, result.error_message = error.code, str(error)
        if body_block:
            source.consecutive_block_count = previous_blocks + 1
        if source.enabled and (
            error.disable
            or (body_block and source.consecutive_block_count >= settings.collector_block_threshold)
        ):
            source.enabled, source.status = False, "blocked"
            source.disabled_at, source.disabled_reason = datetime.now(UTC), error.code
            session.add(
                SourceEvent(
                    source_id=source.id,
                    actor="system",
                    action="disable",
                    reason=error.code,
                    at=source.disabled_at,
                )
            )
    session.commit()
    return result
