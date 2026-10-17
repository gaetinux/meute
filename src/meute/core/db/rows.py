"""Typed access to SQLite rows: the only place where untyped rows are read."""

import sqlite3
from collections.abc import Sequence


def fetch_one(
    conn: sqlite3.Connection, sql: str, params: Sequence[object] = ()
) -> tuple[object, ...] | None:
    """Run `sql` and return its first row, or None."""
    row: tuple[object, ...] | None = conn.execute(sql, params).fetchone()  # pyright: ignore[reportAny] — sqlite3 rows are untyped
    return row


def fetch_all(
    conn: sqlite3.Connection, sql: str, params: Sequence[object] = ()
) -> list[tuple[object, ...]]:
    """Run `sql` and return all its rows."""
    return [tuple(row) for row in conn.execute(sql, params)]  # pyright: ignore[reportAny] — sqlite3 rows are untyped
