"""Postgres integration tests migrate an isolated schema in an explicit test database."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.schema import CreateSchema, DropSchema


@pytest.fixture
def db_engine() -> Iterator[Engine]:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL unset; Postgres integration unverified locally (no Docker)")
    database = make_url(url).database or ""
    if database != "pulso_ci" and not database.startswith("pulso_test"):
        pytest.fail("TEST_DATABASE_URL must name pulso_ci or a dedicated pulso_test* database")
    schema = "test_" + uuid4().hex
    engine = create_engine(url, connect_args={"connect_timeout": 2}, hide_parameters=True)
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
    except OperationalError:
        engine.dispose()
        pytest.skip(
            "Postgres test database unreachable; integration unverified locally (no Docker)"
        )
    isolated = create_engine(
        url,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 2,
            "options": f"-c search_path={schema},public -c timezone=UTC",
        },
    )
    try:
        config = Config(str(Path(__file__).parent / "alembic.ini"))
        with isolated.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield isolated
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text("SET lock_timeout = '3s'"))
            connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
