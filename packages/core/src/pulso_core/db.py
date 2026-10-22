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

    @declared_attr.directive
    def __table_args__(cls) -> tuple[UniqueConstraint, Index]:
        return (
            UniqueConstraint(
                *cls.observation_keys, "raw_payload_id", postgresql_nulls_not_distinct=True
            ),
            Index(None, cls.observation_keys[0], "captured_at"),
        )


def make_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c timezone=UTC -c statement_timeout=10000",
        },
    )


@lru_cache
def _process_engine(pid: int) -> Engine:
    return make_engine(get_settings().database_url.get_secret_value())


def get_engine() -> Engine:
    return _process_engine(os.getpid())


def get_session() -> Session:
    return Session(get_engine())
