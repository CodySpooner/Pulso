"""ml-queue jobs: concurrency 1, lazy imports, each behind its own flag (AGENTS.md §7)."""

import logging
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
