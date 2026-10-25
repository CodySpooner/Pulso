import hashlib
import io
import math
from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from PIL import Image as PILImage
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from pulso_core.models import (
    CollectorRun,
    FxRate,
    Image,
    Listing,
    MatchCandidate,
    RawPayload,
    Store,
)
from pulso_core.models.catalog import EMBEDDING_DIM
from pulso_ml.embeddings import Counts, embed
from pulso_ml.matching.matcher import match
from pulso_ml.matching.score import stored

pytestmark = pytest.mark.db


def turn(plane: int, degrees: float) -> list[float]:
    """A unit vector in plane `plane`; two in one plane have cosine cos(angle between them)."""
    vector = [0.0] * EMBEDDING_DIM
    vector[2 * plane] = math.cos(math.radians(degrees))
    vector[2 * plane + 1] = math.sin(math.radians(degrees))
    return vector


class FakeEncoder:
    """Weight-free and deterministic: an image's red level and a title's length set an angle."""

    def __init__(self) -> None:
        self.seen: list[Any] = []

    def images(self, images: Sequence[PILImage.Image]) -> list[list[float]]:
        self.seen += images
        return [turn(0, image.getpixel((0, 0))[0]) for image in images]  # type: ignore[index]

    def texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.seen += texts
        return [turn(1, len(title)) for title in texts]


def png(red: int) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (8, 8), (red, 0, 0)).save(buffer, "PNG")
    return buffer.getvalue()


class World:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.run = CollectorRun(source_id=6, trigger="manual", status="success")
        session.add(self.run)
        session.flush()
        self.blobs: dict[str, bytes] = {}  # the object store, by storage key

    def listing(self, title: str, red: int | None = None, *, fetched: bool = True) -> Listing:
        """A listing on its own store; `red` adds a main image, stored only when fetched."""
        store = Store(domain=f"s{uuid4().hex[:8]}.example", platform="shopify")
        self.session.add(store)
        self.session.flush()
        listing = Listing(
            source_id=1,
            external_id=uuid4().hex,
            url=f"https://{store.domain}/products/x",
            title=title,
            store_id=store.id,
        )
        self.session.add(listing)
        self.session.flush()
        if red is not None:
            key = None
            if fetched:
                body = png(red)
                digest = hashlib.sha256(body).hexdigest()
                key = f"raw/listing_images/2026/10/25/{digest}.bin.gz"
                self.session.add(
                    RawPayload(
                        source_id=6,
                        run_id=self.run.id,
                        request={},
                        bytes=len(body),
                        sha256=digest,
                        storage_key=key,
                    )
                )
                self.blobs[key] = body
            self.session.add(
                Image(listing_id=listing.id, url=f"{listing.url}.png", position=1, storage_key=key)
            )
        self.session.commit()
        return listing

    def read(self, payload: RawPayload) -> bytes:
        """storage.read_capture's contract: the stored body, checked against its sha256."""
        assert payload.storage_key is not None
        body = self.blobs[payload.storage_key]
        if hashlib.sha256(body).hexdigest() != payload.sha256:
            raise ValueError("Raw capture SHA-256 mismatch")
        return body

    def image(self, listing: Listing) -> Image:
        return self.session.scalars(select(Image).where(Image.listing_id == listing.id)).one()


@pytest.fixture
def world(db_engine: Engine) -> Iterator[World]:
    with Session(db_engine) as session:
        yield World(session)


def row_versions(session: Session) -> list[Any]:
    """Every images and listings row's xmin: an UPDATE, even to equal values, changes it."""
    return list(
        session.execute(
            text(
                "SELECT 'image', id, xmin::text FROM images"
                " UNION ALL SELECT 'listing', id, xmin::text FROM listings ORDER BY 1, 2"
            )
        )
    )


def test_stored_images_and_all_titles_are_embedded_then_a_rerun_writes_nothing(
    world: World,
) -> None:
    stored_image = world.listing("Sunset lamp", red=10)
    unfetched = world.listing("Desk fan", red=20, fetched=False)
    imageless = world.listing("Phone grip")

    assert embed(world.session, FakeEncoder(), world.read) == Counts(
        images=1, titles=3, image_missing=2
    )

    world.session.expire_all()
    assert list(world.image(stored_image).embedding) == pytest.approx(turn(0, 10), abs=1e-6)
    assert world.image(unfetched).embedding is None  # missing, never a zero vector
    for listing in (stored_image, unfetched, imageless):
        assert list(listing.title_embedding) == pytest.approx(turn(1, len(listing.title)))
        assert listing.title_norm == listing.title  # the text its embedding was made from

    before, encoder = row_versions(world.session), FakeEncoder()
    assert embed(world.session, encoder, world.read) == Counts(image_missing=2)
    assert encoder.seen == []
    assert row_versions(world.session) == before


def test_a_changed_title_alone_is_embedded_again(world: World) -> None:
    lamp = world.listing("Sunset lamp", red=10)
    world.listing("Desk fan")
    embed(world.session, FakeEncoder(), world.read)
    lamp.title = "Sunset lamp XL"
    world.session.commit()

    encoder = FakeEncoder()
    assert embed(world.session, encoder, world.read) == Counts(titles=1, image_missing=1)
    assert encoder.seen == ["Sunset lamp XL"]
    world.session.expire_all()
    assert list(lamp.title_embedding) == pytest.approx(turn(1, len("Sunset lamp XL")))


@pytest.mark.parametrize("fault", ["object_missing", "undecodable"])
def test_an_unreadable_image_is_counted_and_the_others_still_embed(
    world: World, caplog: pytest.LogCaptureFixture, fault: str
) -> None:
    bad = world.listing("Sunset lamp", red=10)
    good = world.listing("Desk fan", red=30)
    key = world.image(bad).storage_key
    assert key is not None
    if fault == "object_missing":
        del world.blobs[key]
    else:  # hash-consistent bytes that aren't an image
        world.blobs[key] = b"not an image"
        payload = world.session.scalars(select(RawPayload).where(RawPayload.storage_key == key))
        payload.one().sha256 = hashlib.sha256(b"not an image").hexdigest()
        world.session.commit()
    caplog.set_level("WARNING", logger="pulso.ml.embeddings")

    counts = embed(world.session, FakeEncoder(), world.read)

    assert counts == Counts(images=1, titles=2, image_missing=1, image_unreadable=1)
    assert f"embedding_image_unreadable image_id={world.image(bad).id}" in caplog.text
    world.session.expire_all()
    assert world.image(bad).embedding is None
    assert list(world.image(good).embedding) == pytest.approx(turn(0, 30), abs=1e-6)


def no_rates(session: Session, currency: str, day: date) -> FxRate | None:
    return None


def test_the_matchers_candidates_come_from_the_new_vectors(world: World) -> None:
    a = world.listing("Sunset lamp", red=0)
    b = world.listing("Sunset lamp", red=10)
    world.listing("Sunset lamp", red=90)  # orthogonal image: below the queue band
    assert match(world.session, no_rates).skipped_no_embedding == 3

    embed(world.session, FakeEncoder(), world.read)
    counts = match(world.session, no_rates)

    assert counts.skipped_no_embedding == 0
    pairs = world.session.scalars(select(MatchCandidate)).all()
    assert [(pair.listing_a_id, pair.listing_b_id, pair.status) for pair in pairs] == [
        (a.id, b.id, "pending")  # >= 0.90 but no price: queued, never auto-linked
    ]
    assert pairs[0].image_cos == stored(math.cos(math.radians(10)))
    assert pairs[0].title_cos == stored(1.0)
