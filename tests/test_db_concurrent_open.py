"""Opening the database from several processes, and opening it without migrating."""

import fcntl
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, migrate
from meute.core.db.schema import SCHEMA_VERSION
from meute.core.errors import MigrationError

_WORKER = """
import sys, time
from pathlib import Path
from meute.core.db.connection import Database
db_path, ready, go = (Path(arg) for arg in sys.argv[1:4])
ready.touch()
while not go.exists():
    time.sleep(0.005)
with Database.open(db_path, busy_timeout_ms=30000) as db:
    print(db.schema_version())
"""


def _make_v1(path: Path) -> None:
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, MIGRATIONS[:1])
        conn.execute(
            "INSERT INTO tasks (title, status, priority, created_at, updated_at)"
            " VALUES ('kept', 'todo', 'normal', 'x', 'x')"
        )


def test_two_processes_migrating_a_v1_file_both_succeed(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    _make_v1(path)
    go = tmp_path / "go"
    ready = [tmp_path / "ready-1", tmp_path / "ready-2"]
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(path), str(flag), str(go)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for flag in ready
    ]
    deadline = time.monotonic() + 30
    while not all(flag.exists() for flag in ready) and time.monotonic() < deadline:
        time.sleep(0.005)
    go.touch()
    results = [(w.wait(timeout=60), *w.communicate()) for w in workers]
    assert [(code, err) for code, _out, err in results] == [(0, ""), (0, "")]
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (SCHEMA_VERSION,)
        assert conn.execute("SELECT title FROM tasks").fetchall() == [("kept",)]
    assert sorted(p.name for p in tmp_path.iterdir() if ".bak-" in p.name) == ["meute.db.bak-1"]


def test_lock_file_is_private(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    _make_v1(path)
    Database.open(path, busy_timeout_ms=1000).close()
    assert (tmp_path / "meute.db.lock").stat().st_mode & 0o777 == 0o600


def test_open_existing_refuses_another_version_without_touching_it(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    _make_v1(path)
    before = path.read_bytes()
    names = sorted(p.name for p in tmp_path.iterdir())
    with pytest.raises(
        MigrationError,
        match=rf"^database schema version 1 does not match this meute \({SCHEMA_VERSION}\)$",
    ):
        Database.open_existing(path, busy_timeout_ms=1000)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == names


def test_open_existing_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "absent.db"
    with pytest.raises(FileNotFoundError):
        Database.open_existing(path, busy_timeout_ms=1000)
    assert not path.exists()


def test_open_existing_opens_a_current_database(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).close()
    with Database.open_existing(path, busy_timeout_ms=1000) as db:
        assert db.schema_version() == SCHEMA_VERSION
        assert db.pragma("foreign_keys") == "1"
        assert db.pragma("busy_timeout") == "1000"


def test_schema_version_matches_migrations() -> None:
    assert len(MIGRATIONS) == SCHEMA_VERSION


def test_open_existing_does_not_import_migrations() -> None:
    code = (
        "import sys; import meute.core.db.connection;"
        " sys.exit('meute.core.db.migrations' in sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0


def test_worker_waiting_on_the_lock_rereads_the_version_after_it(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    _make_v1(path)
    go = tmp_path / "go"
    go.touch()
    lock_fd = os.open(tmp_path / "meute.db.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(lock_fd, fcntl.LOCK_EX)
    try:
        worker = subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(path), str(tmp_path / "ready"), str(go)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(1.5)  # long enough for the worker to start and reach the lock
        assert worker.poll() is None
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute("PRAGMA user_version").fetchone() == (1,)
            migrate(conn, None, MIGRATIONS)  # the lock is ours: no second lock, no backup
        backup = tmp_path / "meute.db.bak-1"
        with closing(sqlite3.connect(path)) as conn:
            conn.execute("VACUUM INTO ?", (str(backup),))
        mtime = backup.stat().st_mtime_ns
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)
    out, err = worker.communicate(timeout=60)
    assert (worker.returncode, err) == (0, "")
    assert out.strip() == str(SCHEMA_VERSION)
    assert backup.stat().st_mtime_ns == mtime


def test_failed_migration_releases_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn, pytest.raises(MigrationError):
        migrate(conn, path, ("CREATE TABLE a(x);", "NOT SQL"))
    fd = os.open(tmp_path / "meute.db.lock", os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(fd)


def test_open_existing_leaves_migrations_unloaded(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).close()
    code = (
        "import sys; from pathlib import Path; from meute.core.db.connection import Database;"
        f" Database.open_existing(Path({str(path)!r}), busy_timeout_ms=1000).close();"
        " sys.exit('meute.core.db.migrations' in sys.modules)"
    )
    assert subprocess.run([sys.executable, "-c", code], check=False).returncode == 0
