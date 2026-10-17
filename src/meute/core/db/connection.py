"""The SQLite connection: opening, pragmas, transactions and typed row access."""

import re
import sqlite3
from collections.abc import Callable, Generator
from contextlib import contextmanager
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


def _connect(path: Path | None, pragmas: tuple[str, ...]) -> sqlite3.Connection:
    """Connect to `path` (None: in memory), apply `pragmas` and migrate; close on failure."""
    conn = sqlite3.connect(":memory:" if path is None else path, autocommit=True)
    try:
        for pragma in pragmas:
            conn.execute(pragma)
        migrate(conn, path)
    except BaseException:
        conn.close()
        raise
    return conn


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
        pragmas = (
            f"PRAGMA busy_timeout = {int(busy_timeout_ms)}",
            "PRAGMA journal_mode = WAL",
            "PRAGMA foreign_keys = ON",
        )
        return cls(conn=_connect(path, pragmas), clock=clock)

    @classmethod
    def in_memory(cls, *, clock: Clock = utc_now) -> Self:
        """Open a migrated in-memory database."""
        return cls(conn=_connect(None, ("PRAGMA foreign_keys = ON",)), clock=clock)

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

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection]:
        """Run a `BEGIN IMMEDIATE` transaction in a `with` block.

        It commits on normal exit and rolls back when an exception escapes.
        """
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
