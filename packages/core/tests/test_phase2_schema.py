from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, func, insert, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from pulso_core.models import (
    Image,
    Listing,
    MatchDecision,
    Product,
    ProductDailyFeature,
    ProductNote,
    ProductTag,
    User,
    Workspace,
    WorkspaceSettings,
)
from pulso_core.models.catalog import EMBEDDING_DIM

pytestmark = pytest.mark.db

ALEMBIC_INI = str(Path(__file__).resolve().parents[3] / "alembic.ini")


def make_listing(connection: Connection, external_id: str) -> int:
    return connection.execute(
        insert(Listing)
        .values(source_id=1, external_id=external_id, title="X", url="https://example.test/x")
        .returning(Listing.id)
    ).scalar_one()


def make_product(connection: Connection) -> UUID:
    return connection.execute(
        insert(Product).values(name="Lamp").returning(Product.id)
    ).scalar_one()


def unit_vector(axis: int) -> list[float]:
    return [1.0 if i == axis else 0.0 for i in range(EMBEDDING_DIM)]


def test_phase2_round_trip(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    version = text("SELECT version_num FROM alembic_version")
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0004")
        assert connection.scalar(version) == "0004"
        assert connection.scalar(text("SELECT to_regclass('match_decisions')")) is None
        command.upgrade(config, "head")
        assert connection.scalar(version) == "0024"


def test_feature_gap_flags_refuse_a_lossy_downgrade(db_engine: Engine) -> None:
    config = Config(ALEMBIC_INI)
    version = text("SELECT version_num FROM alembic_version")
    row = {"family": "shp_sellers", "feature_version": "002-x", "coverage": 1, "has_gap": False}
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0017")  # no flags yet: the columns drop
        command.upgrade(config, "head")
        connection.execute(
            insert(ProductDailyFeature).values(
                product_id=make_product(connection),
                feature_date=date(2026, 12, 14),
                features={"shp_sellers": 2},
                gap_flags={"missed_runs": ["2026-12-13"]},
                **row,
            )
        )
        with pytest.raises(DBAPIError, match="lossy downgrade"), connection.begin_nested():
            command.downgrade(config, "0017")
        assert connection.scalar(version) == "0024"


@pytest.mark.parametrize(
    "owner_input",
    [
        "INSERT INTO match_decisions (actor, action, listing_id) VALUES ('owner', 'reject', :l)",
        "INSERT INTO product_notes (id, workspace_id, product_id, author_id, body) "
        "VALUES (gen_random_uuid(), :w, :p, :u, 'note')",
        "INSERT INTO product_tags (workspace_id, product_id, tag) VALUES (:w, :p, 'winner')",
        "INSERT INTO category_mappings VALUES (1, 'lamps', 1, 'manual')",
        "UPDATE settings SET duty_default_bps = 2500",
    ],
    ids=["decision", "note", "tag", "manual-mapping", "duty"],
)
def test_phase2_downgrade_refuses_owner_input(db_engine: Engine, owner_input: str) -> None:
    config = Config(ALEMBIC_INI)
    with db_engine.begin() as connection:
        config.attributes["connection"] = connection
        workspace = connection.execute(
            insert(Workspace).values(name="A").returning(Workspace.id)
        ).scalar_one()
        user = connection.execute(
            insert(User).values(clerk_user_id="user_a").returning(User.id)
        ).scalar_one()
        connection.execute(insert(WorkspaceSettings).values(workspace_id=workspace))
        connection.execute(
            text("INSERT INTO categories (id, name, path) VALUES (1, 'Home', 'Home')")
        )
        params = {"l": make_listing(connection, "g1"), "p": make_product(connection)}
        connection.execute(text(owner_input), {**params, "w": workspace, "u": user})
        with (
            pytest.raises(DBAPIError, match="Phase 2 owner input"),
            connection.begin_nested(),
        ):
            command.downgrade(config, "0004")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0024"


def test_embedding_knn_uses_hnsw(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        listing_ids = [make_listing(connection, f"e{axis}") for axis in range(5)]
        for axis, listing_id in enumerate(listing_ids):
            vector = unit_vector(axis)
            connection.execute(
                insert(Image).values(
                    listing_id=listing_id,
                    url="https://example.test/i.jpg",
                    position=1,
                    embedding=vector,
                )
            )
            connection.execute(
                update(Listing).where(Listing.id == listing_id).values(title_embedding=vector)
            )
        connection.execute(text("SET LOCAL enable_seqscan = off"))
        near_axis_0 = [0.9, 0.1] + [0.0] * (EMBEDDING_DIM - 2)
        for column, owner, index in (
            (Image.embedding, Image.listing_id, "ix_images_embedding"),
            (Listing.title_embedding, Listing.id, "ix_listings_title_embedding"),
        ):
            query = select(owner).order_by(column.cosine_distance(near_axis_0)).limit(20)
            sql = str(query.compile(connection, compile_kwargs={"literal_binds": True}))
            plan = "\n".join(connection.exec_driver_sql("EXPLAIN " + sql).scalars())
            assert f"Index Scan using {index}" in plan
            assert connection.scalars(query).all()[:2] == listing_ids[:2]


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE match_decisions SET reason = 'edited'",
        "DELETE FROM match_decisions",
        "TRUNCATE match_decisions",
    ],
)
def test_match_decisions_are_append_only(db_engine: Engine, mutation: str) -> None:
    with db_engine.begin() as connection:
        connection.execute(
            insert(MatchDecision).values(
                actor="algo",
                action="link",
                listing_id=make_listing(connection, "d1"),
                to_product_id=make_product(connection),
                confidence=Decimal("0.9300"),
            )
        )
        with (
            pytest.raises(DBAPIError, match="match_decisions is append-only"),
            connection.begin_nested(),
        ):
            connection.execute(text(mutation))
        assert connection.scalar(select(func.count()).select_from(MatchDecision)) == 1


def test_two_workspace_notes_and_tags_isolation(db_engine: Engine) -> None:
    with Session(db_engine) as session, session.begin():
        a, b = Workspace(name="A"), Workspace(name="B")
        user, product = User(clerk_user_id="user_a"), Product(name="Lamp")
        session.add_all([a, b, user, product])
        session.flush()
        for workspace in (a, b):
            session.add_all(
                [
                    ProductNote(
                        workspace_id=workspace.id,
                        product_id=product.id,
                        author_id=user.id,
                        body=f"note {workspace.name}",
                    ),
                    ProductTag(workspace_id=workspace.id, product_id=product.id, tag="winner"),
                ]
            )
        session.add(ProductTag(workspace_id=a.id, product_id=product.id, tag="only-a"))
        session.flush()
        for workspace, tags in ((a, ["only-a", "winner"]), (b, ["winner"])):
            notes = select(ProductNote.body).where(ProductNote.workspace_id == workspace.id)
            assert session.scalars(notes).all() == [f"note {workspace.name}"]
            tag_query = select(ProductTag.tag).where(ProductTag.workspace_id == workspace.id)
            assert sorted(session.scalars(tag_query)) == tags
        for statement in (
            insert(ProductTag).values(workspace_id=a.id, product_id=product.id, tag="winner"),
            insert(ProductTag).values(workspace_id=None, product_id=product.id, tag="orphan"),
            insert(ProductNote).values(
                workspace_id=None, product_id=product.id, author_id=user.id, body="orphan"
            ),
        ):
            with pytest.raises(IntegrityError), session.begin_nested():
                session.execute(statement)


def test_settings_duty_not_set_and_cost_ranges(db_engine: Engine) -> None:
    with db_engine.begin() as connection:
        workspace = connection.execute(
            insert(Workspace).values(name="A").returning(Workspace.id)
        ).scalar_one()
        connection.execute(insert(WorkspaceSettings).values(workspace_id=workspace))
        row = connection.execute(
            select(
                WorkspaceSettings.duty_default_bps,
                WorkspaceSettings.returns_bps,
                WorkspaceSettings.customs_fee_minor,
            )
        ).one()
        assert tuple(row) == (None, 0, 0)
        connection.execute(update(WorkspaceSettings).values(duty_default_bps=14500))  # 145%
        for bad in ({"returns_bps": 10001}, {"customs_fee_minor": -1}, {"duty_default_bps": -1}):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(update(WorkspaceSettings).values(**bad))
