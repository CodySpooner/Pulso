from collections.abc import Iterator

from sqlalchemy.orm import Session

from pulso_core.db import get_session


def get_db() -> Iterator[Session]:
    with get_session(statement_timeout=10_000) as session:
        yield session
