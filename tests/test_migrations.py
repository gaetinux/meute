import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from meute.core.db.migrations import current_version, migrate
from meute.core.db.rows import fetch_all
from meute.core.errors import MigrationError

V1 = ("CREATE TABLE a(x);",)
V2 = (*V1, "CREATE TABLE b(x);")


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = fetch_all(
        conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {str(row[0]) for row in rows}


def backups(directory: Path) -> list[Path]:
    return [p for p in directory.iterdir() if ".bak-" in p.name]


def test_upgrading_an_existing_file_backs_it_up_first(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V1)
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V2)
        assert current_version(conn) == 2
        assert "b" in tables(conn)
    with closing(sqlite3.connect(tmp_path / "meute.db.bak-1")) as saved:
        assert tables(saved) == {"a"}


def test_existing_backup_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    (tmp_path / "meute.db.bak-1").write_text("garbage")
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V1)
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V2)
    with closing(sqlite3.connect(tmp_path / "meute.db.bak-1")) as saved:
        assert tables(saved) == {"a"}


def test_fresh_file_makes_no_backup(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V2)
        assert current_version(conn) == 2
    assert backups(tmp_path) == []


def test_failed_migration_rolls_back_and_keeps_version(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    broken = (*V1, "CREATE TABLE c(x); CREATE TABLE broken(")
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V1)
        with pytest.raises(MigrationError, match="migration 2 failed"):
            migrate(conn, path, broken)
        assert current_version(conn) == 1
        assert "c" not in tables(conn)
        assert not conn.in_transaction


def test_newer_database_is_refused_untouched(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, V2)
        with pytest.raises(MigrationError, match=r"version 2 is newer than this meute \(1\)"):
            migrate(conn, path, V1)
        assert current_version(conn) == 2
    assert backups(tmp_path) == []
