"""Schema migrations: numbered SQL files applied in order, each in one transaction."""

import sqlite3
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from meute.core.db.rows import as_integer, fetch_one
from meute.core.errors import MigrationError


def _load_migrations() -> tuple[str, ...]:
    files = sorted(
        (
            f
            for f in resources.files("meute.core.db").joinpath("sql").iterdir()
            if f.name.endswith(".sql")
        ),
        key=lambda f: f.name,
    )
    return tuple(f.read_text(encoding="utf-8") for f in files)


MIGRATIONS: tuple[str, ...] = _load_migrations()


def current_version(conn: sqlite3.Connection) -> int:
    """Return the schema version stored in `PRAGMA user_version`."""
    row = fetch_one(conn, "PRAGMA user_version")
    return as_integer(row[0]) if row else 0


def backup_path(db_path: Path, version: int) -> Path:
    """Return the backup file made before leaving schema `version`, next to the database."""
    return db_path.with_name(f"meute.db.bak-{version}")


def migrate(
    conn: sqlite3.Connection, db_path: Path | None, migrations: Sequence[str] = MIGRATIONS
) -> None:
    """Bring the schema up to `len(migrations)`.

    An existing file database is saved with `VACUUM INTO` before its first migration.
    Each migration runs in one transaction that also bumps `user_version`.

    Raises:
        MigrationError: the database is newer than `migrations`, or a migration failed
            (it is then rolled back entirely).
    """
    version = current_version(conn)
    target = len(migrations)
    if version > target:
        message = f"database schema version {version} is newer than this meute ({target})"
        raise MigrationError(message)
    if version == target:
        return
    if version > 0 and db_path is not None:
        backup = backup_path(db_path, version)
        backup.unlink(missing_ok=True)
        conn.execute("VACUUM INTO ?", (str(backup),))
    for number in range(version + 1, target + 1):
        script = (
            f"BEGIN IMMEDIATE;\n{migrations[number - 1]}\nPRAGMA user_version = {number};\nCOMMIT;"
        )
        try:
            conn.executescript(script)
        except sqlite3.Error as error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            message = f"migration {number} failed: {error}"
            raise MigrationError(message) from error
