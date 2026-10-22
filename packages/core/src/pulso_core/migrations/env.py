from alembic import context
from sqlalchemy import Connection

from pulso_core import models  # noqa: F401 -- register metadata
from pulso_core.db import Base, get_engine


def migrate(connection: Connection | None = None) -> None:
    context.configure(
        connection=connection,
        dialect_name="postgresql",
        target_metadata=Base.metadata,
        literal_binds=connection is None,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    migrate()
else:
    supplied_connection = context.config.attributes.get("connection")
    if supplied_connection is not None:
        migrate(supplied_connection)
    else:
        with get_engine().connect() as connection:
            migrate(connection)
