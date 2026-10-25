"""KW-2 (DEC-292): the weekly Trends set is the approved seeds, then every workspace's confirmed
product keywords, cut at the monthly limit // 5. SQLite and the migrated PostgreSQL schema."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import JSON, DefaultClause, MetaData, create_engine, text
from sqlalchemy.orm import Session

from pulso_core.db import Base
from pulso_core.models import Product, ProductKeyword, Source, User, Workspace
from pulso_core.settings import Settings
from pulso_sources import google_trends as trends
from pulso_sources.framework import Request, Target

pytest_plugins = ("packages.sources.tests.framework.conftest",)
T0 = datetime(2026, 10, 1, tzinfo=UTC)
SEEDS = ["Sunset Lamp", "galaxy projector"]


class World:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.user = User(clerk_user_id="user_fixture")
        self.a, self.b = Workspace(name="A"), Workspace(name="B")
        self.p1, self.p2 = Product(name="Sunset lamp"), Product(name="Star projector")
        session.add_all([self.user, self.a, self.b, self.p1, self.p2])
        session.flush()

    def seeds(self, *keywords: str) -> None:
        self.session.get_one(Source, 3).config = {
            "seed": {
                "version": "seed_v1",
                "status": "approved",
                "decision": "DEC-011",
                "approved_on": "2026-01-01",
                "entries": [
                    {"keyword": k, "geo": "US", "tz": 0, "enabled": True} for k in keywords
                ],
            }
        }

    def decide(
        self,
        workspace: Workspace,
        product: Product,
        keyword: str,
        day: int,
        status: str = "confirmed",
    ) -> None:
        self.session.add(
            ProductKeyword(
                workspace_id=workspace.id,
                product_id=product.id,
                keyword=keyword,
                source="manual",
                status=status,
                decided_by=self.user.id,
                decided_at=T0 + timedelta(days=day),
            )
        )


@pytest.fixture(params=["sqlite", pytest.param("postgres", marks=pytest.mark.db)])
def world(request: pytest.FixtureRequest) -> Iterator[World]:
    if request.param == "postgres":
        engine = request.getfixturevalue("db_engine")  # migrated; source 3 is google_trends
    else:
        engine = create_engine("sqlite://")
        metadata = MetaData()
        for table in Base.metadata.tables.values():
            table.to_metadata(metadata)
        for name in ("sources", "workspaces", "users", "products", "product_keywords"):
            table = metadata.tables[name]
            for column in table.columns:
                if isinstance(column.type, JSON):
                    column.type, column.server_default = JSON(), DefaultClause(text("'{}'"))
            table.create(engine)
        with Session(engine) as session:
            session.add(
                Source(id=3, key="google_trends", name="Google Trends", type="vendor", phase=1)
            )
            session.commit()
    with Session(engine, expire_on_commit=False) as session:
        world = World(session)
        world.seeds(*SEEDS)
        yield world


def keywords(world: World, settings: Settings) -> list[str]:
    world.session.flush()
    return trends.weekly_set(world.session, settings).keywords


def test_off_plans_exactly_the_seeds(
    world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    world.decide(world.a, world.p1, "night light", 0)
    settings.trends_monthly_search_limit = 5  # a cap of 1 applies only with the setting on
    monkeypatch.setattr(trends, "get_settings", lambda: settings)
    world.session.flush()
    assert trends.plan(world.session) == [
        Target("trends", k, [Request(params={**trends.PARAMS, "q": k})]) for k in SEEDS
    ]
    week = trends.weekly_set(world.session, settings)
    assert (week.cap, week.monthly_limit, week.confirmed) == (1, 5, False)


def test_on_seeds_first_then_confirmed_in_a_stable_order(
    world: World, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.trends_confirmed_keywords = True
    a, b, p1, p2 = world.a, world.b, world.p1, world.p2
    world.decide(a, p1, "sunset   LAMP", 0)  # a seed in another case and spacing: the seed stays
    world.decide(a, p1, "star projector", 3)
    world.decide(b, p2, "star projector", 4)  # two workspaces: first among the confirmed
    world.decide(a, p1, "moon lamp", 0)  # earliest confirmation
    world.decide(a, p1, "night light", 1)
    world.decide(a, p2, "night light", 2)  # the same workspace twice still counts once
    world.decide(b, p1, "aurora lamp", 1)  # ties night light on time: A to Z
    world.decide(a, p1, "ufo lamp", 0, "rejected")
    world.decide(b, p2, "lamp, light", 0)  # two keywords in one search: skipped, run goes on
    expected = [*SEEDS, "star projector", "moon lamp", "aurora lamp", "night light"]
    assert keywords(world, settings) == expected
    assert keywords(world, settings) == expected  # the same set every run
    monkeypatch.setattr(trends, "get_settings", lambda: settings)
    assert [t.target_id for t in trends.plan(world.session)] == expected


def test_a_rejection_wins_across_merged_products(world: World, settings: Settings) -> None:
    settings.trends_confirmed_keywords = True
    world.p2.merged_into_id = world.p1.id  # p2's decisions read through on p1 (DEC-263)
    world.decide(world.a, world.p2, "star projector", 0)
    world.decide(world.a, world.p1, "star projector", 1, "rejected")  # the newest decision
    world.decide(world.a, world.p2, "moon lamp", 0)  # only on the merged product: still confirmed
    world.decide(world.b, world.p1, "night light", 0, "rejected")
    world.decide(world.b, world.p2, "aurora lamp", 0, "rejected")
    world.decide(world.b, world.p1, "aurora lamp", 2)  # confirmed later on the survivor
    assert keywords(world, settings) == [*SEEDS, "moon lamp", "aurora lamp"]


def test_the_51st_keyword_is_left_out_at_250(world: World, settings: Settings) -> None:
    settings.trends_confirmed_keywords = True
    for i in range(49):
        world.decide(world.a, world.p1, f"keyword {i:02}", i)
    world.session.flush()
    week = trends.weekly_set(world.session, settings)
    assert (week.cap, len(week.keywords)) == (50, 50)
    assert week.keywords[-1] == "keyword 47" and "keyword 48" not in week.keywords


@pytest.mark.parametrize("limit", [0, 1, 49, 50, 250])
def test_five_mondays_stay_within_the_monthly_limit(
    world: World, settings: Settings, limit: int
) -> None:
    settings.trends_confirmed_keywords, settings.trends_monthly_search_limit = True, limit
    for i in range(60):
        world.decide(world.b, world.p2, f"keyword {i:02}", i)
    planned = keywords(world, settings)
    assert len(planned) * 5 <= limit
    assert len(planned) == min(len(SEEDS) + 60, limit // 5)
    assert planned[: len(SEEDS)] == SEEDS[: limit // 5]  # seeds take the slots first
