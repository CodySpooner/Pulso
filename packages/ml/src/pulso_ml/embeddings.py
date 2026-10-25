"""OpenCLIP image and title embeddings into the vectors M-3 reads (M-2 part b, DEC-269).

Importing this module never imports torch or open_clip: only `openclip()` loads them.
"""

import io
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image as PILImage
from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.orm import Session

from pulso_core.models import Image, Listing, RawPayload

# DEC-237's checkpoint, which fixes vector(512); the weights pinned to one Hugging Face commit.
MODEL = "ViT-B-32"
WEIGHTS_REPO = "laion/CLIP-ViT-B-32-laion2B-s34B-b79K"
WEIGHTS_FILE = "open_clip_model.safetensors"  # sha256 ac4f8c4b…56e6 (DEC-269)
WEIGHTS_REVISION = "1a25a446712ba5ee05982a381eed697ef9b435cf"
MODEL_VERSION = f"{MODEL}/laion2b_s34b_b79k@{WEIGHTS_REVISION[:7]}"
BATCH = 32

# pulso_sources.storage.read_capture, passed in: pulso-sources already depends on pulso-ml.
ReadCapture = Callable[[RawPayload], bytes]
logger = logging.getLogger("pulso.ml.embeddings")


class Encoder(Protocol):
    """Unit vectors of EMBEDDING_DIM floats, one per input, in one space for both kinds."""

    def images(self, images: Sequence[PILImage.Image]) -> Sequence[Any]: ...

    def texts(self, texts: Sequence[str]) -> Sequence[Any]: ...


@dataclass
class Counts:
    images: int = 0
    titles: int = 0
    image_missing: int = 0  # listings left with no image vector: M-3 skips them (DEC-040)
    image_unreadable: int = 0


def openclip() -> Encoder:
    """The pinned checkpoint on CPU; the ml worker image bakes it (HF_HUB_OFFLINE=1 at run)."""
    import open_clip
    import torch
    from huggingface_hub import hf_hub_download

    weights = hf_hub_download(WEIGHTS_REPO, WEIGHTS_FILE, revision=WEIGHTS_REVISION)
    model, _, preprocess = open_clip.create_model_and_transforms(MODEL, pretrained=weights)
    model.eval()
    tokenizer = open_clip.get_tokenizer(MODEL)

    class OpenClip:
        def images(self, images: Sequence[PILImage.Image]) -> Any:
            with torch.inference_mode():
                batch = torch.stack([preprocess(image) for image in images])
                return model.encode_image(batch, normalize=True).numpy()

        def texts(self, texts: Sequence[str]) -> Any:
            with torch.inference_mode():
                return model.encode_text(tokenizer(list(texts)), normalize=True).numpy()

    return OpenClip()


def embed(session: Session, encoder: Encoder, read: ReadCapture) -> Counts:
    """Embed stored images without a vector, then titles whose vector isn't of the current title.

    Idempotent without a key column: an image row's stored copy never changes once set (its
    storage key names the bytes' sha256, DEC-240 h), and `title_norm` keeps the exact text
    each title vector was made from. The model is fixed by the schema (DEC-237 a): another
    checkpoint is a migration that clears both columns. One commit per batch.
    """
    counts = Counts()
    last = 0
    while batch := (
        session.execute(
            select(Image.id, Image.storage_key)
            .where(Image.storage_key.is_not(None), Image.embedding.is_(None), Image.id > last)
            .order_by(Image.id)
            .limit(BATCH)
        )
        .tuples()
        .all()
    ):
        last = batch[-1][0]
        ids, pictures = [], []
        for image_id, key in batch:
            assert key is not None  # the query's filter
            try:
                payload = session.scalars(
                    select(RawPayload)
                    .where(RawPayload.sha256 == digest(key), RawPayload.storage_key == key)
                    .limit(1)
                ).one()
                pictures.append(PILImage.open(io.BytesIO(read(payload))).convert("RGB"))
            except Exception:  # a missing object or bad bytes; retried next run
                logger.warning("embedding_image_unreadable image_id=%s", image_id, exc_info=True)
                counts.image_unreadable += 1
                continue
            ids.append(image_id)
        if ids:
            vectors = encoder.images(pictures)
            session.execute(
                update(Image),
                [{"id": i, "embedding": v} for i, v in zip(ids, vectors, strict=True)],
            )
            counts.images += len(ids)
        session.commit()

    last = 0
    while titles := (
        session.execute(
            select(Listing.id, Listing.title)
            .where(
                or_(
                    Listing.title_embedding.is_(None),
                    Listing.title_norm.is_distinct_from(Listing.title),
                ),
                Listing.id > last,
            )
            .order_by(Listing.id)
            .limit(BATCH)
        )
        .tuples()
        .all()
    ):
        last = titles[-1][0]
        vectors = encoder.texts([title for _, title in titles])
        session.execute(
            update(Listing),
            [
                {"id": i, "title_embedding": v, "title_norm": title}
                for (i, title), v in zip(titles, vectors, strict=True)
            ],
        )
        counts.titles += len(titles)
        session.commit()

    embedded = exists().where(Image.listing_id == Listing.id, Image.embedding.is_not(None))
    counts.image_missing = (
        session.scalar(select(func.count()).select_from(Listing).where(~embedded)) or 0
    )
    return counts


def digest(storage_key: str) -> str:
    """raw/<source>/<yyyy>/<mm>/<dd>/<sha256>.<suffix>.gz names the body's sha256 (DEC-240 g)."""
    return storage_key.rsplit("/", 1)[-1].split(".", 1)[0]
