"""The schema version this meute expects, known without loading the migrations' text."""

import sqlite3

from meute.core.db.rows import as_integer, fetch_one

SCHEMA_VERSION = 4


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version stored in `PRAGMA user_version`."""
    row = fetch_one(conn, "PRAGMA user_version")
    return as_integer(row[0]) if row else 0
