"""ml-queue jobs: concurrency 1, lazy imports, each behind its own flag (AGENTS.md §7)."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pulso_core.db import get_session
from pulso_core.logging import job_id
from pulso_core.settings import get_settings
from pulso_workers.celery_app import app

logger = logging.getLogger("pulso.ml")


def match_listings(task: Any) -> None:
    """M-3 matcher (DEC-249). ponytail: no Beat entry; schedule it once M-2 part b embeds."""
    with job_id.set(task.request.id):
        if not get_settings().matcher_enabled:
            logger.info("matcher_disabled")
            return
        from pulso_ml.matching.matcher import match
        from pulso_sources.fx_frankfurter import rate_as_of

        with get_session() as session:
            counts = match(session, rate_as_of)
        # The shared JSON formatter omits extras; keep the counts in the message.
        logger.info(
            "matcher_done scored=%s linked=%s queued=%s discarded=%s skipped_no_embedding=%s"
            " gtin_linked=%s gtin_queued=%s",
            counts.scored,
            counts.linked,
            counts.queued,
            counts.discarded,
            counts.skipped_no_embedding,
            counts.gtin_linked,
            counts.gtin_queued,
        )


app.task(name="ml.match", bind=True)(match_listings)


def embed_listings(task: Any) -> None:
    """M-2 part b (DEC-269). ponytail: no Beat entry until the ml consumer has the weights."""
    with job_id.set(task.request.id):
        if not get_settings().embeddings_enabled:
            logger.info("embeddings_disabled")
            return
        from pulso_ml import embeddings
        from pulso_sources.storage import read_capture

        with get_session() as session:
            counts = embeddings.embed(session, embeddings.openclip(), read_capture)
        logger.info(
            "embeddings_done model=%s images=%s titles=%s image_missing=%s image_unreadable=%s",
            embeddings.MODEL_VERSION,
            counts.images,
            counts.titles,
            counts.image_missing,
            counts.image_unreadable,
        )


app.task(name="ml.embed", bind=True)(embed_listings)


def compute_features(task: Any, start: str | None = None, end: str | None = None) -> None:
    """Feature store (DEC-275, DEC-278): yesterday (UTC) by default; ISO start..end backfills
    inclusive, one commit per day. ponytail: no Beat entry until the collector host consumes ml."""
    with job_id.set(task.request.id):
        if not get_settings().features_enabled:
            logger.info("features_disabled")
            return
        from pulso_ml.features import daily

        today = datetime.now(UTC).date()
        last = date.fromisoformat(end) if end else today - timedelta(days=1)
        first = date.fromisoformat(start) if start else last
        # Rows are append-only: a day computed before its cutoff would keep a partial row.
        if not first <= last < today:
            raise ValueError(f"features need {first} <= {last} < today ({today}, UTC)")
        with get_session() as session:
            for offset in range((last - first).days + 1):
                day = first + timedelta(days=offset)
                written = daily.run(session, day)
                session.commit()
                logger.info("features_done day=%s written=%s", day, written)


app.task(name="ml.features", bind=True)(compute_features)
