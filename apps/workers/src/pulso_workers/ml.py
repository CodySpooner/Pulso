"""ml-queue jobs: concurrency 1, lazy imports, each behind its own flag (AGENTS.md §7)."""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from pulso_core.alerts import evaluate
from pulso_core.db import get_session
from pulso_core.logging import job_id
from pulso_core.models import Alert, Workspace
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


def days(start: str | None, end: str | None) -> list[date]:
    """ISO start..end inclusive, yesterday (UTC) by default; never a day still being collected."""
    today = datetime.now(UTC).date()
    last = date.fromisoformat(end) if end else today - timedelta(days=1)
    first = date.fromisoformat(start) if start else last
    # Rows are append-only: a day computed before its cutoff would keep a partial row.
    if not first <= last < today:
        raise ValueError(f"need {first} <= {last} < today ({today}, UTC)")
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def score(session: Session, day: date) -> None:
    from pulso_ml.scores import nightly

    written = nightly.run(session, day)
    session.commit()
    logger.info("scores_done day=%s written=%s", day, written)
    evaluate_alerts(session, day)


def evaluate_alerts(session: Session, day: date) -> None:
    """WF-4 rules for day d at its cutoff, so a backfill replays point in time (DEC-334).
    One commit per workspace: a failing one is logged and rolled back, never the scores."""
    from pulso_ml.features.daily import cutoff

    # ponytail: counts the whole table; the ml queue's concurrency 1 keeps other writers out.
    total = select(func.count(Alert.id))
    before = session.execute(total).scalar_one()
    evaluated = skipped = failed = 0
    for workspace_id in session.scalars(select(Workspace.id).order_by(Workspace.id)).all():
        try:
            statuses = evaluate(session, workspace_id, cutoff(day))
            session.commit()
        except Exception:
            session.rollback()
            failed += 1
            logger.exception("alerts_failed day=%s workspace_id=%s", day, workspace_id)
            continue
        evaluated += 1
        skipped += list(statuses.values()).count("skipped")
    logger.info(
        "alerts_done day=%s workspaces=%s fired=%s skipped=%s failed=%s",
        day,
        evaluated,
        session.execute(total).scalar_one() - before,
        skipped,
        failed,
    )


def compute_features(task: Any, start: str | None = None, end: str | None = None) -> None:
    """Feature store (DEC-275, DEC-278): yesterday (UTC) by default; ISO start..end backfills
    inclusive, one commit per day, each day's scores after its rows (DEC-326).
    ponytail: no Beat entry until the collector host consumes ml (imp-284)."""
    with job_id.set(task.request.id):
        if not get_settings().features_enabled:
            logger.info("features_disabled")
            return
        from pulso_ml.features import daily

        todo = days(start, end)
        with get_session() as session:
            for day in todo:
                written = daily.run(session, day)
                session.commit()
                logger.info("features_done day=%s written=%s", day, written)
                score(session, day)


app.task(name="ml.features", bind=True)(compute_features)


def compute_scores(task: Any, day: str | None = None) -> None:
    """SC-6 (DEC-326): one UTC day's scores from its stored feature rows, yesterday by default.
    Behind FEATURES_ENABLED: ml.features runs it after each day, so it has no Beat entry."""
    with job_id.set(task.request.id):
        if not get_settings().features_enabled:
            logger.info("scores_disabled")
            return
        (only,) = days(day, day)
        with get_session() as session:
            score(session, only)


app.task(name="ml.scores", bind=True)(compute_scores)
