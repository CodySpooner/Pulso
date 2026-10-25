"""Listing main images into the raw store, plus pHash (DEC-240); run under the source lock."""

import io
import json
import logging
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from itertools import zip_longest
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener
from urllib.request import Request as URLRequest
from urllib.robotparser import RobotFileParser

from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from pulso_core.models import CollectorRunTarget, Image, Listing, RawPayload
from pulso_core.settings import Settings
from pulso_ml.phash import phash
from pulso_sources.framework import Request, Response, RunDeferred, Target, UpsertStats
from pulso_sources.shopify_stores import NoRedirect, RobotsDisallowed
from pulso_sources.storage import JsonValue

SOURCE, SCOPE, AGENT = "listing_images", "listing_image", "PulsoBot"
MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 40_000_000  # about 6300 x 6300; checked from the header before decoding
# A failed image waits 20 h (so the next daily slot retries it), doubling to at most 30 days.
BACKOFF, BACKOFF_CAP = timedelta(hours=20), timedelta(days=30)
# ponytail: in-process spacing only; a worker restart can send one early request per host.
_next_host: dict[str, float] = {}
logger = logging.getLogger("pulso.sources.listing_images")


# One class per check: a run records only type(exc).__name__ as its error_code (data-06).
class ImageContentType(ValueError):
    pass


class ImageTooLarge(ValueError):
    pass


class ImageUndecodable(ValueError):
    pass


def decode(body: bytes) -> PILImage.Image:
    image = PILImage.open(io.BytesIO(body), formats=["JPEG", "PNG", "WEBP", "GIF"])
    if image.width * image.height > MAX_PIXELS:
        raise ImageTooLarge("pixels")
    image.load()
    return image


def check(response: Response) -> None:
    """Reject before anything is stored: media type, byte cap, pixel cap, a clean decode."""
    media = (response.content_type or "").split(";", 1)[0].strip().lower()
    if media not in MEDIA_TYPES:
        raise ImageContentType()
    body = response.body or b""
    if len(body) > MAX_BYTES:
        raise ImageTooLarge("bytes")
    try:
        decode(body)
    except (ImageTooLarge, PILImage.DecompressionBombError) as exc:
        raise ImageTooLarge("pixels") from exc
    except Exception as exc:  # Pillow signals bad data with OSError, SyntaxError, ValueError...
        raise ImageUndecodable() from exc


def https_host(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        return parts.hostname if parts.scheme == "https" and parts.port in {None, 443} else None
    except ValueError:
        return None


class ImageAdapter:
    parser_version = "listing-images-1"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.deadline = time.monotonic() + settings.collector_wall_time_seconds
        self.robots: dict[str, RobotFileParser] = {}
        self.robots_bodies: dict[str, bytes] = {}
        self.delays: dict[str, float] = {}

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        url, host = str(request.params["url"]), str(request.params["host"])
        delay = max(0.0, _next_host.get(host, 0) - time.monotonic())
        if time.monotonic() + delay >= self.deadline:
            raise RunDeferred("wall_time_budget")
        if delay:
            time.sleep(delay)
        _next_host[host] = time.monotonic() + max(
            60 / self.settings.image_requests_per_minute, self.delays.get(host, 0)
        )
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            try:
                response = opener.open(
                    URLRequest(url, headers={"User-Agent": user_agent}),
                    timeout=self.settings.collector_request_timeout_seconds,
                )
            except HTTPError as error:
                response = error
            with response:
                result = Response(
                    response.read(MAX_BYTES + 1),  # One byte past the cap proves oversize.
                    response.code,
                    response.headers.get("Content-Type"),
                    response.headers.get("ETag"),
                    headers=dict(response.headers.items()),
                )
        except URLError as error:
            raise ConnectionError("image_transport") from error
        if "image_id" not in request.params:
            self.robots_bodies[host] = result.body or b""
        elif 200 <= (result.status_code or 0) < 300:
            try:
                check(result)
            except ValueError as exc:
                name = type(exc).__name__
                logger.warning(
                    "image_rejected image_id=%s reason=%s",
                    request.params["image_id"],
                    name,
                    extra={"source": SOURCE, "error_type": name},
                )
                raise
        return result

    @staticmethod
    def parse(body: bytes) -> list[int]:
        try:
            image = decode(body)
        except UnidentifiedImageError:
            return []  # robots.txt or an empty-plan manifest; fetch vetted every image body
        return [phash(image)]

    @staticmethod
    def upsert(
        session: Session, records: Sequence[int], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        if not records:
            return UpsertStats()
        image = session.get_one(Image, payload.request["image_id"])
        if image.storage_key is not None:
            return UpsertStats(unchanged=1)
        # The raw capture is the stored copy: one object named by its sha256 (DEC-240).
        image.storage_key, image.phash = payload.storage_key, records[0]
        return UpsertStats(updated=1)

    def robots_requests(self, host: str) -> Iterator[Request]:
        yield Request(params={"url": f"https://{host}/robots.txt", "host": host})
        # Resumed only after a 2xx capture; otherwise the target fails and the host's images
        # skip this run unattempted (fail closed, no backoff).
        robots = RobotFileParser()
        robots.parse(self.robots_bodies[host].decode("utf-8-sig", "replace").splitlines())
        rate = robots.request_rate(AGENT)
        self.delays[host] = max(
            float(robots.crawl_delay(AGENT) or 0), rate.seconds / rate.requests if rate else 0
        )
        _next_host[host] = max(_next_host.get(host, 0), time.monotonic() + self.delays[host])
        self.robots[host] = robots

    def image_requests(self, image_id: int, url: str, host: str) -> Iterator[Request]:
        robots = self.robots.get(host)
        if robots is None:
            return
        if not robots.can_fetch(AGENT, url):
            raise RobotsDisallowed()
        yield Request(params={"url": url, "host": host, "image_id": image_id})


def plan(session: Session, *, settings: Settings) -> tuple[ImageAdapter, list[Target]]:
    """Each current listing's main image without a stored copy, on a listed host, not in backoff.

    The main image is the lowest position, newest row on a tie (rows are never deleted, so a
    replaced image leaves its old row at the same position).
    """
    ranked = (
        select(
            Image.id,
            Image.url,
            Image.storage_key,
            func.row_number()
            .over(partition_by=Image.listing_id, order_by=(Image.position, Image.id.desc()))
            .label("rank"),
        )
        .join(Listing, Listing.id == Image.listing_id)
        .where(Listing.delisted_at.is_(None))
        .subquery()
    )
    pending = session.execute(
        select(ranked.c.id, ranked.c.url)
        .where(ranked.c.rank == 1, ranked.c.storage_key.is_(None))
        .order_by(ranked.c.id)
    ).all()
    # Attempted failures only: a deferred or skipped target has no capture and is not 'failed'.
    # ponytail: grouped over all image targets via (scope, target_id, captured_at); move the
    # backoff into SQL if planning slows past ~100k failed targets.
    failures = {
        target_id: (count, last if last.tzinfo else last.replace(tzinfo=UTC))
        for target_id, count, last in session.execute(
            select(
                CollectorRunTarget.target_id,
                func.count(),
                func.max(CollectorRunTarget.captured_at),
            )
            .where(
                CollectorRunTarget.scope == SCOPE,
                CollectorRunTarget.status != "success",
                or_(
                    CollectorRunTarget.raw_payload_id.is_not(None),
                    CollectorRunTarget.status == "failed",
                ),
            )
            .group_by(CollectorRunTarget.target_id)
        )
    }
    session.commit()
    adapter = ImageAdapter(settings)
    hosts = {host.lower() for host in settings.image_hosts}
    limit = settings.image_requests_per_minute * settings.collector_wall_time_seconds // 60
    now = datetime.now(UTC)
    queues: dict[str, list[Target]] = {}
    unlisted = waiting = 0
    for image_id, url in pending:
        host = https_host(url)
        count, last = failures.get(str(image_id), (0, None))
        if host is None or host not in hosts:
            unlisted += 1
        elif last and last + min(BACKOFF * 2 ** min(count - 1, 6), BACKOFF_CAP) > now:
            waiting += 1
        elif len(queue := queues.setdefault(host, [])) < limit:
            queue.append(Target(SCOPE, str(image_id), adapter.image_requests(image_id, url, host)))
    targets = [Target(f"{SCOPE}_robots", host, adapter.robots_requests(host)) for host in queues]
    # Round-robin, so one host's spacing never idles the others.
    targets += [t for group in zip_longest(*queues.values()) for t in group if t is not None]
    logger.info(
        "listing_images_plan pending=%s targets=%s unlisted_host=%s backoff=%s",
        len(pending),
        len(targets),
        unlisted,
        waiting,
        extra={"source": SOURCE},
    )
    if not targets:
        # A target-less run is recorded failed (and queues a catch-up): capture the plan offline.
        manifest: dict[str, JsonValue] = {
            "pending": len(pending),
            "unlisted_host": unlisted,
            "backoff": waiting,
        }
        body = json.dumps(manifest).encode()
        targets.append(Target(f"{SCOPE}_plan", "empty", [Request(manifest, "json", body)]))
    return adapter, targets
