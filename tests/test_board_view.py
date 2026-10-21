"""Tests of the dashboard view model."""

from pathlib import Path

from meute.core.board_view import (
    LaunchBash,
    LaunchClaude,
    RepoEntry,
    SessionEntry,
    ShowSession,
    confirm_stop_text,
    enter_action,
    error_text,
    new_action,
    stop_target,
)
from meute.core.project import RepoId
from support import BOARD_ID_B as _ID_B
from support import BOARD_REPO_1 as _REPO_1
from support import BOARD_REPO_2 as _REPO_2
from support import BOARD_SESSION_A as _SESSION_A
from support import board_data as _data


def test_enter_on_session_shows_and_on_repo_launches_there() -> None:
    data = _data()
    assert enter_action(SessionEntry(row=data.sessions[1])) == ShowSession(session_id=_ID_B)
    assert enter_action(RepoEntry(repo=_REPO_1)) == LaunchBash(cwd=_REPO_1.path, repo_id=RepoId(1))


def test_new_on_session_launches_in_its_cwd_and_repo() -> None:
    data = _data()
    assert new_action(SessionEntry(row=data.sessions[0]), data) == LaunchBash(
        cwd=_SESSION_A.cwd, repo_id=None
    )
    assert new_action(SessionEntry(row=data.sessions[1]), data) == LaunchBash(
        cwd=Path("/srv/work"), repo_id=None
    )
    assert new_action(RepoEntry(repo=_REPO_2), data) == LaunchClaude(
        cwd=_REPO_2.path, repo_id=RepoId(2)
    )


def test_stop_target_is_none_for_a_repo() -> None:
    data = _data()
    assert stop_target(RepoEntry(repo=_REPO_1)) is None
    assert stop_target(SessionEntry(row=data.sessions[0])) == _SESSION_A


def test_confirm_and_error_texts() -> None:
    assert confirm_stop_text("build") == 'Stop "build"? y: yes · any other key: no'
    assert error_text("db locked") == "Error: db locked"
