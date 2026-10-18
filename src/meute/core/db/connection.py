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

from meute.core.db.rows import fetch_one
from meute.core.db.schema import SCHEMA_VERSION, current_version
from meute.core.errors import InvalidInput, MigrationError
from meute.core.instants import utc_now

Clock = Callable[[], datetime]

_PRAGMA_NAME = re.compile(r"[a-z_]+")


# tests/test_mutants_db.py monkeypatches this name: keep it a module-level function.
def migrate(conn: sqlite3.Connection, db_path: Path | None) -> None:
    """Migrate `conn`; the migrations are loaded on first use, so `open_existing` never pays."""
    from meute.core.db import migrations  # noqa: PLC0415 — keeps `open_existing` light

    migrations.migrate(conn, db_path)


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


def _require_current_schema(conn: sqlite3.Connection) -> None:
    version = current_version(conn)
    if version != SCHEMA_VERSION:
        message = f"database schema version {version} does not match this meute ({SCHEMA_VERSION})"
        raise MigrationError(message)


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
    def open_existing(cls, path: Path, *, busy_timeout_ms: int, clock: Clock = utc_now) -> Self:
        """Open the database file at `path` as it is: never create, migrate or back it up.

        Meant for hot paths (hooks) that must stay cheap and must not write the schema.

        Raises:
            FileNotFoundError: there is no database file at `path`.
            MigrationError: the schema version is not the one this meute expects.
        """
        if not path.is_file():
            raise FileNotFoundError(path)
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=rw", uri=True, autocommit=True)
        try:
            conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
            conn.execute("PRAGMA foreign_keys = ON")
            _require_current_schema(conn)
        except BaseException:
            conn.close()
            raise
        return cls(conn=conn, clock=clock)

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

    def data_version(self) -> int:
        """Return `PRAGMA data_version`: it changes when another connection wrote the file."""
        return int(self.pragma("data_version"))

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
