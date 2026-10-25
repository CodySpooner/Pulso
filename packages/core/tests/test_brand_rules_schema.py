"""popular_brand_rules (migration 0011, DEC-277): a workspace's Google popular brand list."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from pulso_core.models import PopularBrandRule, User, Workspace

pytestmark = pytest.mark.db

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")


def rule(workspace: Workspace, user: User, brand: str, action: str = "hide") -> PopularBrandRule:
    return PopularBrandRule(
        workspace_id=workspace.id,
        brand_norm=brand.lower(),
        brand=brand,
        action=action,
        created_by=user.id,
    )


def test_two_workspace_brand_rule_isolation(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        a, b, user = Workspace(name="A"), Workspace(name="B"), User(clerk_user_id="user_a")
        session.add_all([a, b, user])
        session.flush()
        session.add_all([rule(a, user, "Acme"), rule(b, user, "ACME", "show")])
        session.add(rule(a, user, "Indie"))
        session.flush()
        expected = {a: [("acme", "hide"), ("indie", "hide")], b: [("acme", "show")]}
        for workspace, rules in expected.items():
            query = select(PopularBrandRule.brand_norm, PopularBrandRule.action).where(
                PopularBrandRule.workspace_id == workspace.id
            )
            assert sorted(session.execute(query).tuples()) == rules
        values = {"brand": "Acme", "action": "hide", "created_by": user.id}
        for statement in (
            # One rule per workspace and brand, whatever the case.
            insert(PopularBrandRule).values(workspace_id=a.id, brand_norm="acme", **values),
            insert(PopularBrandRule).values(workspace_id=None, brand_norm="acme", **values),
            insert(PopularBrandRule).values(
                workspace_id=a.id, brand_norm="other", brand="Other", action="mute",
                created_by=user.id,
            ),
            # brand_norm is lower(brand), as the major-brand rule reads brands.
            insert(PopularBrandRule).values(
                workspace_id=a.id, brand_norm="Other", brand="Other", action="hide",
                created_by=user.id,
            ),
        ):  # fmt: skip
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(statement)
        # Current preference, not history: a plain delete is allowed.
        session.delete(session.get_one(PopularBrandRule, (a.id, "indie")))
        session.flush()
        count = select(func.count()).select_from(PopularBrandRule)
        assert session.scalar(count) == 2


def test_downgrade_refuses_to_drop_brand_rules(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        workspace = connection.execute(
            insert(Workspace).values(name="A").returning(Workspace.id)
        ).scalar_one()
        user = connection.execute(
            insert(User).values(clerk_user_id="user_a").returning(User.id)
        ).scalar_one()
        connection.execute(
            insert(PopularBrandRule).values(
                workspace_id=workspace, brand_norm="acme", brand="Acme", action="hide",
                created_by=user,
            )
        )  # fmt: skip
        with pytest.raises(DBAPIError, match="brand rules"), connection.begin_nested():
            command.downgrade(config, "0010")
        connection.execute(text("DELETE FROM popular_brand_rules"))
        command.downgrade(config, "0010")
        assert connection.scalar(text("SELECT to_regclass('popular_brand_rules')")) is None
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT to_regclass('popular_brand_rules')")) is not None
