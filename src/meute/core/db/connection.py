"""The SQLite connection: opening, pragmas, transactions and typed row access."""

import re
import sqlite3
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Self

from meute.core.db.migrations import migrate
from meute.core.db.rows import fetch_one
from meute.core.errors import InvalidInput
from meute.core.instants import utc_now

Clock = Callable[[], datetime]

_PRAGMA_NAME = re.compile(r"[a-z_]+")


@dataclass(frozen=True, slots=True, kw_only=True)
class Database:
    """An open, migrated database and the clock used to stamp its rows."""

    conn: sqlite3.Connection
    clock: Clock

    @classmethod
    def open(cls, path: Path, *, busy_timeout_ms: int, clock: Clock = utc_now) -> Self:
        """Open (creating it and its folders) and migrate the database file at `path`.

        Raises:
            MigrationError: the schema cannot be brought up to date.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, autocommit=True)
        try:
            conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn, path)
        except BaseException:
            conn.close()
            raise
        return cls(conn=conn, clock=clock)

    @classmethod
    def in_memory(cls, *, clock: Clock = utc_now) -> Self:
        """Open a migrated in-memory database."""
        conn = sqlite3.connect(":memory:", autocommit=True)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            migrate(conn, None)
        except BaseException:
            conn.close()
            raise
        return cls(conn=conn, clock=clock)

    def now(self) -> datetime:
        """Return the current instant according to the clock."""
        return self.clock()

    def schema_version(self) -> int:
        """Return the schema version of the database."""
        return int(self.pragma("user_version"))

    def pragma(self, name: str) -> str:
        """Return the value of the pragma `name` as text.

        Raises:
            InvalidInput: `name` does not match `[a-z_]+`.
        """
        if not _PRAGMA_NAME.fullmatch(name):
            message = f"invalid pragma name: {name!r}"
            raise InvalidInput(message)
        row = fetch_one(self.conn, f"PRAGMA {name}")
        return str(row[0]) if row else ""

    def transaction(self) -> AbstractContextManager[sqlite3.Connection]:
        """Return a context manager running a `BEGIN IMMEDIATE` transaction.

        It commits on normal exit and rolls back when an exception escapes.
        """
        return self._transaction()

    @contextmanager
    def _transaction(self) -> Generator[sqlite3.Connection]:
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()

    def __enter__(self) -> Self:
        """Return self."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection."""
        self.close()
