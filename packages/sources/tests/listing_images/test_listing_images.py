"""DEC-240: image fetch through the real run lifecycle; generated images, mocked transport."""

import gzip
import hashlib
import io
import itertools
import json
import logging
import sqlite3
import time
from collections.abc import Callable, Iterator
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest
from PIL import Image as PILImage
from sqlalchemy import ARRAY, JSON, Integer, MetaData, create_engine, event, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, attributes
from sqlalchemy.schema import DefaultClause

from pulso_core.db import Base
from pulso_core.models import (
    CollectorRun,
    CollectorRunTarget,
    Image,
    Listing,
    RawPayload,
    Source,
    SourceEvent,
)
from pulso_core.settings import Settings
from pulso_ml.phash import phash
from pulso_sources import framework, listing_images, storage
from pulso_sources.framework import Response, enqueue_run, execute_run, lifecycle

A, B = "cdn.example.test", "img.example.test"
ALLOW = Response(b"User-agent: *\nAllow: /\n", 200, "text/plain")
START = datetime(2026, 10, 25, 6, tzinfo=UTC)


def png(seed: int = 1, size: tuple[int, int] = (64, 64), mode: str = "RGB") -> bytes:
    out = io.BytesIO()
    PILImage.new(mode, size, (seed * 40 % 256, 80, 160) if mode == "RGB" else 0).save(out, "PNG")
    return out.getvalue()


def image(seed: int = 1) -> Response:
    return Response(png(seed), 200, "image/png")


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        s3_access_key_id="fixture",
        s3_secret_access_key="fixture",
        collectors_live=True,
        pulso_bot_contact="https://github.com/CodySpooner/Pulso/blob/main/docs/BOT.md",
        image_hosts=[A, B],
        collector_block_threshold=2,
    )


@pytest.fixture
def session(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    adapters: Any = sqlite3.adapters
    monkeypatch.setitem(adapters, (list, sqlite3.PrepareProtocol), json.dumps)
    metadata = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(metadata)
    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.connection.create_function(
            "num_nonnulls", -1, lambda *xs: sum(x is not None for x in xs)
        )
    for name in (
        "sources",
        "collector_runs",
        "raw_payloads",
        "collector_run_targets",
        "source_events",
        "listings",
        "images",
    ):
        table = metadata.tables[name]
        for column in table.columns:
            if column.name == "id":
                column.type = Integer()
            if isinstance(column.type, (JSONB, ARRAY)):
                column.type = JSON()
                if column.server_default is not None:
                    column.server_default = DefaultClause(text("'{}'"))
        table.create(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            Source(
                id=6,
                key="listing_images",
                name="Listing images",
                type="public_endpoint",
                phase=2,
                enabled=True,
            )
        )
        session.commit()

        def utc(source: Source, *_: Any) -> None:  # sqlite drops the offset Postgres keeps
            if source.retry_not_before:
                attributes.set_committed_value(
                    source, "retry_not_before", source.retry_not_before.replace(tzinfo=UTC)
                )

        event.listen(Source, "refresh", utc)
        try:
            yield session
        finally:
            event.remove(Source, "refresh", utc)
    engine.dispose()


class Net:
    def __init__(self) -> None:
        self.now = START
        self.replies: dict[str, Any] = {}
        self.calls: list[tuple[str, datetime, dict[str, str]]] = []
        self.objects: dict[str, bytes] = {}

    def open(self, request: Any, *, timeout: int) -> Any:
        url = request.full_url
        self.calls.append((url, self.now, dict(request.header_items())))
        reply = self.replies[url]  # Unscripted HTTP is always a test failure.
        if isinstance(reply, list):
            reply = reply.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        result = io.BytesIO(reply.body or b"")
        result.code = reply.status_code  # type: ignore[attr-defined]
        result.headers = {"Content-Type": reply.content_type, **reply.headers}  # type: ignore[attr-defined]
        return result

    def sleep(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)

    def hits(self, url: str) -> list[datetime]:
        return [at for called, at, _ in self.calls if called == url]


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Net:
    net = Net()
    s3 = Mock()
    s3.put_object.side_effect = lambda **kw: net.objects.setdefault(kw["Key"], kw["Body"])
    s3.get_object.side_effect = lambda **kw: {"Body": io.BytesIO(net.objects[kw["Key"]])}
    monkeypatch.setattr(storage, "make_client", lambda _: s3)
    monkeypatch.setattr(storage, "get_settings", lambda: settings)
    monkeypatch.setattr(framework, "is_linked_worktree", lambda _: False)
    monkeypatch.setattr(listing_images, "_next_host", {})
    monkeypatch.setattr(listing_images, "build_opener", lambda *_: Mock(open=net.open))
    clock = Mock(now=lambda _=None: net.now)
    monkeypatch.setattr(lifecycle, "datetime", clock)
    monkeypatch.setattr(listing_images, "datetime", clock)
    monkeypatch.setattr(time, "monotonic", lambda: net.now.timestamp())
    monkeypatch.setattr(time, "sleep", net.sleep)
    net.replies[f"https://{A}/robots.txt"] = ALLOW
    net.replies[f"https://{B}/robots.txt"] = ALLOW
    return net


def add_listing(session: Session, *urls: str, delisted: bool = False) -> list[Image]:
    n = session.scalar(select(func.count()).select_from(Listing)) or 0
    listing = Listing(
        source_id=6,
        external_id=f"l{n}",
        title="Lamp",
        url="https://store.test/p",
        delisted_at=START if delisted else None,
    )
    session.add(listing)
    session.flush()
    images = [
        Image(listing_id=listing.id, url=url, position=position)
        for position, url in enumerate(urls, 1)
    ]
    session.add_all(images)
    session.commit()
    return images


def run(session: Session, settings: Settings) -> CollectorRun:
    adapter, targets = listing_images.plan(session, settings=settings)
    queued = enqueue_run(session, source_id=6, trigger="manual", publish=lambda _: None)
    return execute_run(session, queued.id, adapter, targets, settings=settings)


def target(session: Session, run: CollectorRun, img: Image) -> CollectorRunTarget:
    return session.get_one(CollectorRunTarget, (run.id, "listing_image", str(img.id)))


def test_fresh_main_image_stored_once_then_rerun_sends_nothing(
    session: Session, settings: Settings, net: Net
) -> None:
    main, second = add_listing(session, f"https://{A}/main.png", f"https://{A}/second.png")
    add_listing(session, f"https://{A}/gone.png", delisted=True)
    add_listing(session, "https://unlisted.test/x.png")
    add_listing(session, f"http://{A}/plain.png")
    net.replies[main.url] = image()
    result = run(session, settings)
    assert result.status == "success" and result.http_requests == 2
    assert [url for url, _, _ in net.calls] == [f"https://{A}/robots.txt", main.url]
    assert all(h["User-agent"].startswith("PulsoBot/0.1 (+https://") for _, _, h in net.calls)
    session.refresh(main)
    assert main.storage_key is not None
    assert hashlib.sha256(png()).hexdigest() in main.storage_key
    assert [gzip.decompress(body) for body in net.objects.values()].count(png()) == 1
    assert main.phash == phash(PILImage.open(io.BytesIO(png())))
    session.refresh(second)
    assert second.storage_key is None and second.phash is None
    stored = len(net.objects)
    rerun = run(session, settings)
    assert len(net.calls) == 2 and rerun.http_requests == 0
    # Nothing left to fetch still succeeds: one offline plan capture, so no catch-up run.
    assert rerun.status == "success" and len(net.objects) == stored + 1
    manifest = session.scalars(select(RawPayload).order_by(RawPayload.id.desc())).first()
    assert manifest is not None
    assert manifest.request == {"pending": 2, "unlisted_host": 2, "backoff": 0}


@pytest.mark.parametrize(
    "body,content_type,error",
    [
        (lambda: b"<html></html>", "text/html", "ImageContentType"),
        (lambda: bytes(listing_images.MAX_BYTES + 1), "image/jpeg", "ImageTooLarge"),
        # A 42-megapixel 1-bit PNG is a few KB: rejected from its header, never decoded.
        (lambda: png(size=(7000, 6000), mode="1"), "image/png", "ImageTooLarge"),
        (lambda: png()[:60], "image/png", "ImageUndecodable"),
        (lambda: b"\xff\xd8\xff\xe0 not a jpeg", "image/jpeg", "ImageUndecodable"),
    ],
    ids=["content-type", "oversize", "pixels", "truncated", "garbage"],
)
def test_rejected_bodies_are_logged_and_never_stored(
    session: Session,
    settings: Settings,
    net: Net,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    body: Callable[[], bytes],
    content_type: str,
    error: str,
) -> None:
    (img,) = add_listing(session, f"https://{A}/bad")
    net.replies[img.url] = Response(body(), 200, content_type)
    monkeypatch.setattr(logging.getLogger("pulso"), "propagate", True)
    with caplog.at_level(logging.WARNING, "pulso"):
        result = run(session, settings)
    assert result.error_code == error and target(session, result, img).status == "failed"
    assert f"image_rejected image_id={img.id} reason={error}" in caplog.text
    session.refresh(img)
    assert img.storage_key is None and img.phash is None
    # Only robots.txt was captured: the rejected body never reached the object store.
    assert session.scalar(select(func.count()).select_from(RawPayload)) == 1
    assert len(net.objects) == 1


def test_failed_image_backs_off_then_retries(
    session: Session, settings: Settings, net: Net
) -> None:
    (img,) = add_listing(session, f"https://{A}/flaky.png")
    net.replies[img.url] = [Response(b"", 404, "text/plain"), image()]
    assert target(session, run(session, settings), img).status == "partial"
    net.now += timedelta(hours=19)
    assert run(session, settings).status == "success"  # still waiting: nothing requested
    assert len(net.hits(img.url)) == 1
    net.now += timedelta(hours=2)
    run(session, settings)
    assert len(net.hits(img.url)) == 2
    session.refresh(img)
    assert img.storage_key is not None


@pytest.mark.parametrize("status", [403, 429, 430])
def test_consecutive_blocks_disable_once_and_stop_the_run(
    session: Session, settings: Settings, net: Net, status: int
) -> None:
    first, second = (add_listing(session, f"https://{A}/{n}.png")[0] for n in (1, 2))
    blocked = Response(b"", status, "text/plain")
    net.replies[first.url] = blocked
    result = run(session, settings)
    # The first block stops the run: the second image is never requested.
    assert result.error_message == f"http_{status}" and not net.hits(second.url)
    net.replies[f"https://{A}/robots.txt"] = blocked
    for _ in range(3):
        run(session, settings)
    events = session.scalars(select(SourceEvent)).all()
    assert [(e.action, e.reason) for e in events] == [
        ("disable", f"consecutive_blocks:http_{status}")
    ]
    assert len(net.calls) == 3  # robots and the first image, then one blocked robots.txt
    assert not session.get_one(Source, 6).enabled


def test_retry_after_is_honoured(session: Session, settings: Settings, net: Net) -> None:
    (img,) = add_listing(session, f"https://{A}/busy.png")
    busy = Response(b"", 503, "text/plain", headers={"Retry-After": "120"})
    net.replies[img.url] = [busy, image()]
    assert run(session, settings).status == "success"
    first, second = net.hits(img.url)
    assert second - first >= timedelta(seconds=120)


def test_per_host_spacing_caps_requests_and_crawl_delay_slows_it(
    session: Session, settings: Settings, net: Net
) -> None:
    settings.image_requests_per_minute = 6
    net.replies[f"https://{B}/robots.txt"] = Response(
        b"User-agent: *\nCrawl-delay: 20\n", 200, "text/plain"
    )
    for host, count in ((A, 4), (B, 3)):
        for n in range(count):
            (img,) = add_listing(session, f"https://{host}/{n}.png")
            net.replies[img.url] = image(n)
    assert run(session, settings).status == "success"
    for host, spacing, count in ((A, 10, 5), (B, 20, 4)):
        times = [at for url, at, _ in net.calls if url.startswith(f"https://{host}/")]
        assert len(times) == count
        assert all(b - a >= timedelta(seconds=spacing) for a, b in itertools.pairwise(times))
    # Round-robin: B is not starved behind all of A's waits.
    assert [url.split("/")[2] for url, _, _ in net.calls[:4]] == [A, B, A, B]


def test_robots_disallow_skips_the_host_and_unavailable_robots_never_backs_off(
    session: Session, settings: Settings, net: Net
) -> None:
    (blocked,) = add_listing(session, f"https://{A}/private/x.png")
    (other,) = add_listing(session, f"https://{B}/x.png")
    net.replies[f"https://{A}/robots.txt"] = Response(
        b"User-agent: PulsoBot\nDisallow: /private/\n", 200, "text/plain"
    )
    net.replies[f"https://{B}/robots.txt"] = Response(b"", 404, "text/plain")
    result = run(session, settings)
    assert [url for url, _, _ in net.calls] == [
        f"https://{A}/robots.txt",
        f"https://{B}/robots.txt",
    ]
    assert target(session, result, blocked).status == "failed"
    # An unavailable robots.txt fails closed without counting against the host's images.
    assert target(session, result, other).status == "partial"
    net.replies[f"https://{B}/robots.txt"] = ALLOW
    net.replies[other.url] = image()
    run(session, settings)
    assert len(net.hits(blocked.url)) == 0 and len(net.hits(other.url)) == 1


@pytest.mark.parametrize("off", ["source", "collectors_live"])
def test_flag_or_live_guard_off_sends_nothing(
    session: Session, settings: Settings, net: Net, off: str
) -> None:
    (img,) = add_listing(session, f"https://{A}/x.png")
    net.replies[img.url] = image()
    if off == "source":
        session.get_one(Source, 6).enabled = False
        session.commit()
        run(session, settings)
    else:
        settings.collectors_live = False
        with pytest.raises(framework.CollectorsLiveDisabled):
            run(session, settings)
    assert net.calls == [] and not net.objects


def test_registered_worker_path_fetches_on_the_images_job(
    session: Session, settings: Settings, net: Net, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pulso_workers import registration, tasks

    monkeypatch.setattr(registration, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "get_session", lambda: nullcontext(session))
    monkeypatch.setattr(tasks, "AdvisoryLock", lambda _: Mock(acquire=Mock(return_value=True)))
    with pytest.raises(ValueError):
        tasks.PLANS["listing_images"](session, session.get_one(Source, 6), "catalog")
    (img,) = add_listing(session, f"https://{A}/x.png")
    net.replies[img.url] = image()
    queued = enqueue_run(session, source_id=6, trigger="manual", publish=lambda _: None)
    tasks.collect_run(queued.id)
    session.expire_all()
    assert session.get_one(CollectorRun, queued.id).status == "success"
    assert session.get_one(Image, img.id).phash is not None
