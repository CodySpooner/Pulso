"""Product keywords (KW-1, DEC-281): the Trends tab's search keywords. Candidates come from the
product's titles on every read; only this workspace's confirm, reject or typed-in keyword is
stored, and a later decision updates its row. Nothing here calls a source: the weekly Trends set
(KW-2, DEC-292) is `google_trends.weekly_set`, which this page and the Monday job count with."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from pulso_api.auth import current_principal
from pulso_api.keywords import Gram, Key, grams, key, normalize, suggest
from pulso_api.routers.products import DB, CurrentPrincipal, live_product, with_merged
from pulso_core.models import Listing, Product, ProductKeyword
from pulso_core.settings import Settings, get_settings
from pulso_sources.google_trends import WeeklySet, normal, weekly_set

router = APIRouter(prefix="/v1/products", dependencies=[Depends(current_principal)])
Untracked = Literal["budget", "disabled", "comma"]


def searchable(keyword: str) -> str:
    keyword = normalize(keyword)
    if not key(keyword):
        raise ValueError("A keyword needs at least one letter or digit.")
    return keyword


class KeywordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
        AfterValidator(searchable),
    ]
    status: Literal["confirmed", "rejected"]


class Keyword(BaseModel):
    keyword: str  # casefolded, spacing collapsed
    relevance: float | None  # 0–1 from the product's current titles; null: no title holds it
    as_of: AwareDatetime  # the newest listing title read (its last_seen_at)
    source: Literal["title", "manual"]  # manual: typed in, not from a title
    status: Literal["candidate", "confirmed", "rejected"]  # candidate: not decided yet
    decided_at: AwareDatetime | None
    tracked: bool | None  # confirmed only: in the weekly Google Trends set (KW-2)
    # Why a confirmed keyword is out: the set is full, TRENDS_CONFIRMED_KEYWORDS is off, or it
    # holds a comma (Trends takes one keyword per search).
    untracked_reason: Untracked | None


class TrendsBudget(BaseModel):
    """The weekly Google Trends set across every workspace, counted as the Monday job plans it."""

    enabled: bool  # TRENDS_CONFIRMED_KEYWORDS; off, confirmed keywords are saved, never fetched
    weekly_used: int  # keywords in the set: approved seeds first, then confirmed ones
    weekly_cap: int  # monthly_limit // 5: a five-Monday month stays within the monthly limit
    monthly_limit: int  # SerpApi searches a UTC month (TRENDS_MONTHLY_SEARCH_LIMIT)
    as_of: AwareDatetime  # when this was counted


class KeywordList(BaseModel):
    """Decided keywords and up to 12 candidates, by relevance (typed-in ones last), then A to Z."""

    keywords: list[Keyword]
    trends: TrendsBudget


class Read:
    """A product's scored titles and the workspace's newest decision per keyword."""

    def __init__(self, session: Session, workspace_id: UUID, product: Product) -> None:
        titles = session.execute(
            select(Listing.title, Listing.last_seen_at).where(Listing.product_id == product.id)
        ).all()
        self.scored: dict[Key, Gram] = grams([product.name, *(row.title for row in titles)])
        self.as_of: datetime = max(
            (row.last_seen_at for row in titles), default=product.first_seen_at
        )
        self.decided: dict[Key, ProductKeyword] = {}
        # Across the products merged into this one, as notes and tags are read (DEC-263).
        for row in session.scalars(
            select(ProductKeyword)
            .where(
                ProductKeyword.workspace_id == workspace_id,
                ProductKeyword.product_id.in_(with_merged(product.id)),
            )
            .order_by(ProductKeyword.decided_at)
        ):
            self.decided[key(row.keyword)] = row

    def keywords(self, week: WeeklySet) -> KeywordList:
        def relevance(keyword: str) -> float | None:
            found = self.scored.get(key(keyword))
            return found.relevance if found else None

        tracked = {normal(keyword) for keyword in week.keywords}

        def untracked(keyword: str) -> Untracked | None:
            if normal(keyword) in tracked:
                return None
            if not week.confirmed:
                return "disabled"
            return "comma" if "," in keyword else "budget"

        keywords = [
            Keyword(
                keyword=row.keyword,
                relevance=relevance(row.keyword),
                as_of=self.as_of,
                source="title" if row.source == "title" else "manual",
                status="confirmed" if row.status == "confirmed" else "rejected",
                decided_at=row.decided_at,
                tracked=untracked(row.keyword) is None if row.status == "confirmed" else None,
                untracked_reason=untracked(row.keyword) if row.status == "confirmed" else None,
            )
            for row in self.decided.values()
        ] + [
            Keyword(
                keyword=keyword,
                relevance=score,
                as_of=self.as_of,
                source="title",
                status="candidate",
                decided_at=None,
                tracked=None,
                untracked_reason=None,
            )
            for keyword, score in suggest(self.scored, skip=self.decided.keys())
        ]
        keywords.sort(key=lambda k: (k.relevance is None, -(k.relevance or 0), k.keyword))
        budget = TrendsBudget(
            enabled=week.confirmed,
            weekly_used=len(week.keywords),
            weekly_cap=week.cap,
            monthly_limit=week.monthly_limit,
            as_of=datetime.now(UTC),
        )
        return KeywordList(keywords=keywords, trends=budget)


AppSettings = Annotated[Settings, Depends(get_settings)]


@router.get("/{product_id}/keywords", response_model=KeywordList)
def list_product_keywords(
    product_id: UUID, principal: CurrentPrincipal, session: DB, settings: AppSettings
) -> KeywordList:
    read = Read(session, principal.workspace_id, live_product(session, product_id))
    return read.keywords(weekly_set(session, settings))


@router.post("/{product_id}/keywords", response_model=KeywordList)
def set_product_keyword(
    product_id: UUID,
    body: KeywordIn,
    principal: CurrentPrincipal,
    session: DB,
    settings: AppSettings,
) -> KeywordList:
    """Confirm or reject a candidate, or add a keyword by hand (confirmed). A plural or case
    variant of a decided keyword decides that keyword. Repeating a decision changes nothing."""
    product = live_product(session, product_id)
    read = Read(session, principal.workspace_id, product)
    k = key(body.keyword)
    newest = read.decided.get(k)
    if newest is not None and newest.status == body.status:
        return read.keywords(weekly_set(session, settings))
    found = read.scored.get(k)
    stmt = insert(ProductKeyword).values(
        workspace_id=principal.workspace_id,
        product_id=product.id,
        keyword=newest.keyword if newest else body.keyword,
        relevance=Decimal(str(found.relevance)) if found else None,  # at this first decision
        source="title" if found else "manual",
        status=body.status,
        decided_by=principal.user_id,
    )
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=["workspace_id", "product_id", "keyword"],
            set_={"status": body.status, "decided_by": principal.user_id, "decided_at": func.now()},
        )
    )
    session.commit()
    return Read(session, principal.workspace_id, product).keywords(weekly_set(session, settings))
