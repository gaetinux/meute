"""Tests that kill the mutants plan 6c left alive (docs/dev/mutants/2026-plan-6c-python.md)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest

from meute.core.board_sessions import board_session_order
from meute.core.db.connection import Database
from meute.core.db.schema import read_schema_version
from meute.core.doctor import (
    claude_check,
    database_check,
    git_check,
    options_check,
    tmux_check,
)
from meute.core.state_capture import capture, capture_board
from support import board_data

# --- meute.core.doctor: every line carries its own name, whatever its level


@pytest.mark.parametrize(
    ("output", "level"),
    [(None, "fail"), ("tmux x", "fail"), ("tmux 3.1", "fail"), ("tmux 3.2", "warn")],
)
def test_tmux_lines_are_named_tmux(output: str | None, level: str) -> None:
    check = tmux_check(output)
    assert (check.level.value, check.name) == (level, "tmux")


@pytest.mark.parametrize(("output", "level"), [(None, "fail"), ("git version 2.35.1", "fail")])
def test_git_lines_are_named_git(output: str | None, level: str) -> None:
    check = git_check(output)
    assert (check.level.value, check.name) == (level, "git")


@pytest.mark.parametrize(
    ("output", "level"), [(None, "fail"), ("x", "warn"), ("2.1.300", "warn"), ("2.1.301", "ok")]
)
def test_claude_lines_are_named_claude(output: str | None, level: str) -> None:
    check = claude_check(output)
    assert (check.level.value, check.name) == (level, "claude")


def test_a_missing_option_line_is_named_options() -> None:
    check = options_check("")
    assert (check.level.value, check.name) == ("fail", "options")


@pytest.mark.parametrize(("version", "level"), [(None, "warn"), (4, "warn"), (6, "fail")])
def test_database_lines_are_named_database(version: int | None, level: str) -> None:
    check = database_check("~/meute.db", version, 5)
    assert (check.level.value, check.name) == (level, "database")


# --- meute.core.db.schema.read_schema_version


@pytest.fixture
def read_only_folder(tmp_path: Path) -> Iterator[Path]:
    """A folder holding a closed WAL database, then made read-only (restored for clean-up)."""
    folder = tmp_path / "ro"
    folder.mkdir()
    Database.open(folder / "meute.db", busy_timeout_ms=1000).close()
    (folder / "meute.db").chmod(0o444)
    folder.chmod(0o555)
    yield folder
    folder.chmod(0o755)


def test_a_closed_database_in_a_read_only_folder_is_read(read_only_folder: Path) -> None:
    # Only an immutable open reads it: any other open needs a -wal or -shm next to it.
    assert read_schema_version(read_only_folder / "meute.db") == 5


def test_the_wal_of_a_vanished_writer_is_left_as_it_is(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    db = Database.open(source / "meute.db", busy_timeout_ms=1000)
    try:
        copy = tmp_path / "copy"
        copy.mkdir()
        for name in ("meute.db", "meute.db-wal", "meute.db-shm"):
            _ = shutil.copy(source / name, copy / name)  # as a crashed writer leaves them
    finally:
        db.close()
    before = {p.name: p.stat().st_size for p in copy.iterdir()}
    assert read_schema_version(copy / "meute.db") == 5
    # A read-write connection would checkpoint the -wal into the database and delete it.
    assert {p.name: p.stat().st_size for p in copy.iterdir()} == before


# --- meute.core.state_capture.capture_board (made by the final refactor of plan 6b)


def test_capture_board_captures_in_the_board_order() -> None:
    data = board_data()
    assert capture_board(data) == capture(data, board_session_order(data))
    assert len(capture_board(data)) == len(data.sessions)
