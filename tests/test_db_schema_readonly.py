"""`read_schema_version` reads `user_version` without creating or changing any file."""

import sqlite3
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS
from meute.core.db.schema import read_schema_version


def _listing(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_migrated_database_reports_the_latest_version(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).close()
    assert read_schema_version(path) == len(MIGRATIONS)


def test_wal_database_leaves_no_new_file(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).close()
    before = _listing(tmp_path)
    assert read_schema_version(path) == len(MIGRATIONS)
    assert _listing(tmp_path) == before


def test_missing_file_is_none_and_not_created(tmp_path: Path) -> None:
    path = tmp_path / "absent.db"
    assert read_schema_version(path) is None
    assert _listing(tmp_path) == []


def test_text_file_is_not_a_database(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    path.write_text("this is not a database, but long enough to be read as one" * 10)
    with pytest.raises(sqlite3.DatabaseError):
        read_schema_version(path)


def test_delete_mode_database_gets_no_wal_or_shm(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 3")
    conn.execute("CREATE TABLE t (x)")
    conn.commit()
    conn.close()
    before = _listing(tmp_path)
    assert read_schema_version(path) == 3
    assert _listing(tmp_path) == before


def test_path_with_space_and_hash(tmp_path: Path) -> None:
    folder = tmp_path / "my dir #1"
    folder.mkdir()
    path = folder / "a b#c.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 7")
    conn.close()
    assert read_schema_version(path) == 7


def test_database_in_use_by_another_connection(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000):
        assert read_schema_version(path) == len(MIGRATIONS)


def test_empty_file_reads_as_version_zero_and_stays_empty(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    path.touch()
    assert read_schema_version(path) == 0
    assert path.stat().st_size == 0
    assert _listing(tmp_path) == ["meute.db"]
