import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS
from meute.core.db.rows import fetch_all
from meute.core.errors import InvalidInput


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = fetch_all(
        conn, "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {str(row[0]) for row in rows}


def test_open_creates_file_with_wal_and_latest_schema(tmp_path: Path) -> None:
    path = tmp_path / "sub/meute.db"
    with Database.open(path, busy_timeout_ms=5000) as db:
        assert path.exists()
        assert db.schema_version() == len(MIGRATIONS) == 1
        assert (
            db.pragma("journal_mode"),
            db.pragma("foreign_keys"),
            db.pragma("busy_timeout"),
        ) == (
            "wal",
            "1",
            "5000",
        )


def test_schema_has_plan_1_tables() -> None:
    with Database.in_memory() as db:
        assert tables(db.conn) == {
            "projects",
            "repos",
            "project_repos",
            "tasks",
            "task_notes",
            "task_events",
        }


def test_in_memory_is_migrated_with_foreign_keys_and_clock() -> None:
    fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    with Database.in_memory(clock=lambda: fixed) as db:
        assert (db.schema_version(), db.pragma("foreign_keys"), db.now()) == (1, "1", fixed)


def test_reopening_is_idempotent_and_makes_no_backup(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    for _ in range(2):
        with Database.open(path, busy_timeout_ms=5000) as db:
            assert db.schema_version() == 1
    assert not [p for p in tmp_path.iterdir() if ".bak-" in p.name]


@pytest.mark.parametrize(
    "name", ["", "journal-mode", "Journal_Mode", "foreign keys", "user_version; DROP TABLE tasks"]
)
def test_pragma_rejects_malformed_names(name: str) -> None:
    with Database.in_memory() as db, pytest.raises(InvalidInput):
        db.pragma(name)


class _Boom(Exception):  # noqa: N818 — test-only marker
    pass


def _insert_then_fail(db: Database) -> None:
    with db.transaction() as conn:
        conn.execute("INSERT INTO projects(name, name_key, created_at) VALUES ('a', 'a', 'x')")
        raise _Boom


def test_transaction_rolls_back_on_error() -> None:
    with Database.in_memory() as db:
        with pytest.raises(_Boom):
            _insert_then_fail(db)
        assert fetch_all(db.conn, "SELECT id FROM projects") == []


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=5000) as db, db.transaction() as conn:
        conn.execute("INSERT INTO projects(name, name_key, created_at) VALUES ('a', 'a', 'x')")
    with closing(sqlite3.connect(path)) as conn:
        assert fetch_all(conn, "SELECT name FROM projects") == [("a",)]
