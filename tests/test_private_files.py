"""meute's database, backups, state and logs are private to the user, whatever the umask."""

import os
import sqlite3
from collections.abc import Generator
from contextlib import closing
from pathlib import Path

import pytest

from meute.claude.settings import write_settings
from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, migrate
from meute.core.db.projects import create_project
from meute.core.paths import Paths
from meute.core.session import SessionId
from meute.ingest.log import log_failure
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")


@pytest.fixture(autouse=True)
def umask_022() -> Generator[None]:
    previous = os.umask(0o022)
    try:
        yield
    finally:
        _ = os.umask(previous)


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _paths(tmp_path: Path) -> Paths:
    return Paths.from_roots(
        config_home=tmp_path / "config", data_home=tmp_path / "data", state_home=tmp_path / "state"
    )


def test_data_and_state_folders_are_private(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.ensure_dirs()
    assert _mode(paths.db_file.parent) == 0o700
    assert _mode(paths.state_dir) == 0o700
    assert _mode(tmp_path / "data") == 0o755  # the XDG roots are not meute's
    assert _mode(tmp_path / "state") == 0o755


def test_existing_data_and_state_folders_are_made_private(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    for folder in (paths.db_file.parent, paths.state_dir):
        folder.mkdir(parents=True, mode=0o755)
    paths.ensure_dirs()
    assert _mode(paths.db_file.parent) == 0o700
    assert _mode(paths.state_dir) == 0o700


def test_new_database_and_its_wal_files_are_private(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000) as db:
        _ = create_project(db, "p")
        assert _mode(path) == 0o600
        assert _mode(tmp_path / "meute.db-wal") == 0o600
        assert _mode(tmp_path / "meute.db-shm") == 0o600


def test_existing_database_is_made_private(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    Database.open(path, busy_timeout_ms=1000).close()
    path.chmod(0o644)
    Database.open(path, busy_timeout_ms=1000).close()
    assert _mode(path) == 0o600


def test_backup_before_a_migration_is_private(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, MIGRATIONS[:1])
    Database.open(path, busy_timeout_ms=1000).close()
    assert _mode(tmp_path / "meute.db.bak-1") == 0o600


def test_settings_folders_are_private(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "meute"
    _ = write_settings(state_dir, SID, ["meute"])
    assert _mode(state_dir) == 0o700
    assert _mode(state_dir / "sessions") == 0o700
    assert _mode(state_dir / "sessions" / SID) == 0o700


def test_ingest_log_does_not_follow_a_symlink(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    target = tmp_path / "elsewhere"
    target.write_text("")
    (state_dir / "ingest.log").symlink_to(target)
    log_failure(state_dir, "hook", ValueError("boom"), FIXED)
    assert target.read_text() == ""


def test_ingest_log_folder_is_private(tmp_path: Path) -> None:
    state_dir = tmp_path / "state" / "meute"
    log_failure(state_dir, "hook", ValueError("boom"), FIXED)
    assert _mode(state_dir) == 0o700
    assert _mode(state_dir / "ingest.log") == 0o600
