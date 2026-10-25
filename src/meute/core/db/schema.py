"""The schema version this meute expects, known without loading the migrations' text."""

import sqlite3
from contextlib import closing
from pathlib import Path

from meute.core.db.rows import as_integer, fetch_one

SCHEMA_VERSION = 5


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version stored in `PRAGMA user_version`."""
    row = fetch_one(conn, "PRAGMA user_version")
    return as_integer(row[0]) if row else 0


def read_schema_version(path: Path) -> int | None:
    """Return the schema version of the database at `path`, or None when there is no file.

    The file is opened read-only: nothing is created, migrated or backed up. A WAL database with
    no `-wal` file (closed cleanly, nobody using it) is opened `immutable`: a plain read-only
    connection would create `-wal` and `-shm` next to it. `immutable` also ignores a hot
    rollback journal, so a crashed writer's last transaction is not seen.

    Raises:
        sqlite3.Error: the file exists but is not a readable database.
    """
    if not path.exists():
        return None
    resolved = path.resolve()
    wal = resolved.with_name(resolved.name + "-wal")
    mode = "mode=ro" if wal.exists() else "mode=ro&immutable=1"
    with closing(sqlite3.connect(f"{resolved.as_uri()}?{mode}", uri=True)) as conn:
        return current_version(conn)
