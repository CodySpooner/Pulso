"""Dedicated PostgreSQL sessions: key zero for Beat, source ids for execution."""

from sqlalchemy import Connection, text

from pulso_core.db import get_engine

NAMESPACE = 0x50554C53


class AdvisoryLock:
    def __init__(self, key: int) -> None:
        self.key = key
        self.connection: Connection | None = None

    def acquire(self) -> bool:
        self.connection = get_engine().connect().execution_options(isolation_level="AUTOCOMMIT")
        # A pooled session must never retain the lock after this owner closes it.
        self.connection.detach()
        return bool(
            self.connection.scalar(
                text("SELECT pg_try_advisory_lock(:namespace, :key)"),
                {"namespace": NAMESPACE, "key": self.key},
            )
        )

    def held(self) -> bool:
        connection = self.connection
        if connection is None or connection.closed or connection.invalidated:
            return False
        return bool(
            connection.scalar(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                    "AND pid = pg_backend_pid() AND classid = :namespace AND objid = :key "
                    "AND objsubid = 2 AND granted)"
                ),
                {"namespace": NAMESPACE, "key": self.key},
            )
        )

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
