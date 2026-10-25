"""Amazon best-seller ranks: the owner's CSV only (DEC-279).

No usable official API (PA-API retired, Creators API ineligible) and no scraping, so Pulso
never sends a request to Amazon. The owner must obtain each file lawfully.
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_core.models import AmazonRank, RawPayload
from pulso_core.money import to_minor
from pulso_sources.framework import CollectorsLiveDisabled, Request, Response, UpsertStats

if TYPE_CHECKING:
    from pulso_sources.imports import ImportData


class Row(BaseModel):
    asin: str
    title: str
    category: str
    rank: int
    rank_kind: str
    price: Decimal | None = None
    currency: str
    rating: Decimal | None = None
    review_count: int | None = None
    gtins: str | None = None
    observed_for: date | None = None


class ImportAdapter:
    parser_version = "amazon-csv-v1"

    def __init__(self, data: ImportData) -> None:
        if data.csv is None:
            raise ValueError("Amazon imports use the CSV template")
        self.rows = data.csv.rows

    def fetch(self, request: Request, *, user_agent: str) -> Response:
        raise CollectorsLiveDisabled("Amazon is CSV only")

    def parse(self, body: bytes) -> Sequence[Row]:
        return [Row.model_validate(row) for row in self.rows]

    def upsert(
        self, session: Session, records: Sequence[Row], payload: RawPayload, *, parser_version: str
    ) -> UpsertStats:
        if not records:
            return UpsertStats()
        ids = session.scalars(
            insert(AmazonRank)
            .on_conflict_do_nothing(
                index_elements=[*AmazonRank.observation_keys, "raw_payload_id", "parser_version"]
            )
            .returning(AmazonRank.id),
            [
                {
                    "asin": row.asin,
                    "category": row.category,
                    "rank_kind": row.rank_kind,
                    "rank": row.rank,
                    "title": row.title,
                    "price_minor": None if row.price is None else to_minor(row.price, row.currency),
                    "currency": row.currency,
                    "rating": row.rating,
                    "review_count": row.review_count,
                    "gtins": row.gtins,
                    "observed_for": row.observed_for or payload.captured_at.date(),
                    "captured_at": payload.captured_at,
                    "raw_payload_id": payload.id,
                    "parser_version": parser_version,
                }
                for row in records
            ],
        ).all()
        return UpsertStats(inserted=len(ids), unchanged=len(records) - len(ids))
