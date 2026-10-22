"""Shared synchronous database primitives; engines are lazy and process-local."""

import os
from datetime import date, datetime
from functools import lru_cache
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    MetaData,
    String,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, declared_attr, mapped_column

from pulso_core.settings import get_settings


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_N_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class BigId:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class CreatedAt:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WorkspaceOwned:
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)


class Observation:
    """Subclasses name the entity key, including dimensions of shipping quotes."""

    observation_keys: ClassVar[tuple[str, ...]]
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    observed_for: Mapped[date]
    raw_payload_id: Mapped[int] = mapped_column(ForeignKey("raw_payloads.id"))
    parser_version: Mapped[str] = mapped_column(String(80), server_default="1")

    @declared_attr.directive
    def __table_args__(cls) -> tuple[UniqueConstraint, Index]:
        return (
            UniqueConstraint(
                *cls.observation_keys,
                "raw_payload_id",
                "parser_version",
                postgresql_nulls_not_distinct=True,
            ),
            Index(None, cls.observation_keys[0], "captured_at"),
        )


def make_engine(url: str, *, statement_timeout: int | None = None) -> Engine:
    options = "-c timezone=UTC"
    if statement_timeout is not None:
        options += f" -c statement_timeout={statement_timeout}"
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": options,
        },
    )


@lru_cache
def _process_engine(pid: int, statement_timeout: int | None) -> Engine:
    return make_engine(
        get_settings().database_url.get_secret_value(), statement_timeout=statement_timeout
    )


def get_engine(*, statement_timeout: int | None = None) -> Engine:
    return _process_engine(os.getpid(), statement_timeout)


def get_session(*, statement_timeout: int | None = None) -> Session:
    return Session(get_engine(statement_timeout=statement_timeout))
