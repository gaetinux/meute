"""Tests of the dashboard view model."""

from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from meute.core.board_view import (
    BoardData,
    LaunchBash,
    RepoEntry,
    SessionEntry,
    ShowSession,
    board_entries,
    board_lines,
    confirm_stop_text,
    enter_action,
    entry_key,
    entry_line_indexes,
    error_text,
    new_action,
    repo_line,
    session_line,
    stop_target,
)
from meute.core.project import RepoId
from support import BOARD_ID_A as _ID_A
from support import BOARD_ID_B as _ID_B
from support import BOARD_REPO_1 as _REPO_1
from support import BOARD_REPO_2 as _REPO_2
from support import BOARD_SESSION_A as _SESSION_A
from support import board_data as _data


def test_board_lines(snapshot: SnapshotAssertion) -> None:
    assert board_lines(_data()) == snapshot


def test_board_lines_empty(snapshot: SnapshotAssertion) -> None:
    assert board_lines(BoardData(sessions=(), repos=(), orphans=(), home=None)) == snapshot


def test_entries_are_sessions_then_repos() -> None:
    data = _data()
    assert board_entries(data) == (
        SessionEntry(row=data.sessions[0]),
        SessionEntry(row=data.sessions[1]),
        RepoEntry(repo=_REPO_1),
        RepoEntry(repo=_REPO_2),
    )


def test_entry_keys_are_stable_and_distinct() -> None:
    keys = [entry_key(entry) for entry in board_entries(_data())]
    assert keys == [f"session:{_ID_A}", f"session:{_ID_B}", "repo:1", "repo:2"]
    assert len(set(keys)) == len(keys)


def test_enter_on_session_shows_and_on_repo_launches_there() -> None:
    data = _data()
    assert enter_action(SessionEntry(row=data.sessions[1])) == ShowSession(session_id=_ID_B)
    assert enter_action(RepoEntry(repo=_REPO_1)) == LaunchBash(cwd=_REPO_1.path, repo_id=RepoId(1))


def test_new_on_session_launches_in_its_cwd_and_repo() -> None:
    data = _data()
    assert new_action(SessionEntry(row=data.sessions[0])) == LaunchBash(
        cwd=_SESSION_A.cwd, repo_id=RepoId(1)
    )
    assert new_action(SessionEntry(row=data.sessions[1])) == LaunchBash(
        cwd=Path("/srv/work"), repo_id=None
    )
    assert new_action(RepoEntry(repo=_REPO_2)) == LaunchBash(cwd=_REPO_2.path, repo_id=RepoId(2))


def test_stop_target_is_none_for_a_repo() -> None:
    data = _data()
    assert stop_target(RepoEntry(repo=_REPO_1)) is None
    assert stop_target(SessionEntry(row=data.sessions[0])) == _SESSION_A


def test_confirm_and_error_texts() -> None:
    assert confirm_stop_text("build") == 'Stop "build"? y: yes · any other key: no'
    assert error_text("db locked") == "Error: db locked"


def test_entry_line_indexes_point_at_each_entry_line() -> None:
    data = _data()
    assert entry_line_indexes(data) == (3, 4, 7, 8)
    lines = board_lines(data)
    assert [lines[i] for i in entry_line_indexes(data)] == [
        session_line(data.sessions[0], data.home),
        session_line(data.sessions[1], data.home),
        repo_line(_REPO_1),
        repo_line(_REPO_2),
    ]


def test_entry_line_indexes_skip_the_no_sessions_placeholder() -> None:
    data = BoardData(sessions=(), repos=(_REPO_1, _REPO_2), orphans=(), home=None)
    assert entry_line_indexes(data) == (6, 7)
    assert entry_line_indexes(BoardData(sessions=(), repos=(), orphans=(), home=None)) == ()
