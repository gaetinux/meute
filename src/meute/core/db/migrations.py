"""Schema migrations: numbered SQL files applied in order, each in one transaction."""

import fcntl
import os
import sqlite3
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from importlib import resources
from pathlib import Path

from meute.core.db.schema import current_version
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


def backup_path(db_path: Path, version: int) -> Path:
    """Return the backup file made before leaving schema `version`, next to the database."""
    return db_path.with_name(f"meute.db.bak-{version}")


def lock_path(db_path: Path) -> Path:
    """Return the lock file that serialises migrations of `db_path`, next to it."""
    return db_path.with_name(f"{db_path.name}.lock")


@contextmanager
def _migration_lock(db_path: Path | None) -> Generator[None]:
    """Hold an exclusive `flock` on the database's lock file (nothing for in-memory ones)."""
    if db_path is None:
        yield
        return
    fd = os.open(lock_path(db_path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def migrate(
    conn: sqlite3.Connection, db_path: Path | None, migrations: Sequence[str] = MIGRATIONS
) -> None:
    """Bring the schema up to `len(migrations)`.

    An existing file database is saved with `VACUUM INTO` before its first migration.
    Each migration runs in one transaction that also bumps `user_version`.

    Concurrent processes are serialised by an exclusive lock on `<db>.lock`; the version is read
    after the lock is taken, so a process that waited finds the work done and does nothing.

    Raises:
        MigrationError: the database is newer than `migrations`, or a migration failed
            (it is then rolled back entirely).
    """
    with _migration_lock(db_path):
        _migrate_locked(conn, db_path, migrations)


def _migrate_locked(
    conn: sqlite3.Connection, db_path: Path | None, migrations: Sequence[str]
) -> None:
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
