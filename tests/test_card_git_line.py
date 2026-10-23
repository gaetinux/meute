"""Tests of the Git state on line 3 of the session cards."""

from dataclasses import replace
from pathlib import Path

import pytest

from meute.core.board_sessions import board_sessions
from meute.core.board_view import BoardData, SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.git_folder import git_folder
from meute.core.git_state import GitState
from meute.core.sessions_view import SessionInfo, ViewState
from meute.core.sessions_view_text import card_more_lines
from meute.core.statusline import StatuslineData
from meute.core.styled import plain
from support import BOARD_SESSION_A, board_data

_MINUS = chr(0x2212)
_STATE = GitState(
    branch="feat/x", detached=None, upstream=True, ahead=2, behind=1, dirty=True, added=5, removed=3
)
_CASES = {
    "clean": (replace(_STATE, dirty=False, ahead=0, behind=0, added=0, removed=0), "feat/x"),
    "dirty": (replace(_STATE, ahead=0, behind=0, added=0, removed=0), "feat/x*"),
    "counts": (replace(_STATE, ahead=0, behind=0), f"feat/x* +5 {_MINUS}3"),
    "ahead-behind": (replace(_STATE, dirty=False, added=0, removed=0), "feat/x ↑2 ↓1"),
    "not-pushed": (
        replace(_STATE, upstream=False, ahead=0, behind=0, dirty=False, added=0, removed=0),
        "feat/x (not pushed)",
    ),
    "detached": (
        GitState(branch=None, detached="abc1234", upstream=False, ahead=0, behind=0, dirty=False),
        "(detached abc1234)",
    ),
}


def _info(
    git: GitState | None,
    *,
    metrics: StatuslineData | None = None,
    details: ClaudeDetails | None = None,
) -> SessionInfo:
    row = SessionRow(session=BOARD_SESSION_A, has_pane=True, displayed=False)
    return SessionInfo(row=row, details=details, metrics=metrics, group="g", git=git)


def _third(info: SessionInfo, width: int = 80) -> str:
    return plain(card_more_lines(info, width=width)[-1])


@pytest.mark.parametrize("name", list(_CASES))
def test_line_3_shows_the_git_state(name: str) -> None:
    state, text = _CASES[name]
    assert _third(_info(state)) == f"    └ {text}"


@pytest.mark.parametrize("name", list(_CASES))
def test_line_3_is_cut_on_a_narrow_card(name: str) -> None:
    state, _ = _CASES[name]
    line = _third(_info(state), width=9)
    assert len(line) == 9
    assert line.endswith("…")


def test_line_3_adds_the_claude_worktree_name_then_the_last_tool() -> None:
    info = _info(
        _STATE,
        metrics=StatuslineData(worktree_name="wt", worktree_branch="ignored"),
        details=ClaudeDetails(last_tool="Edit"),
    )
    assert _third(info) == f"    └ feat/x* +5 {_MINUS}3 ↑2 ↓1 · wt · Edit"


def test_a_bash_session_with_a_git_state_has_line_3() -> None:
    lines = card_more_lines(_info(_CASES["dirty"][0]), width=80)
    assert [plain(line) for line in lines] == ["    └ feat/x*"]


def test_without_git_state_the_branch_of_the_worktree_stays() -> None:
    info = _info(
        None,
        metrics=StatuslineData(worktree_name="wt", worktree_branch="b"),
        details=ClaudeDetails(last_tool="Edit"),
    )
    assert _third(info) == "    └ b · Edit"
    assert card_more_lines(info, width=80) == card_more_lines(replace(info, git=None), width=80)


def test_git_folder_uses_an_absolute_worktree_path() -> None:
    metrics = StatuslineData(worktree_path="/srv/wt")
    assert git_folder(BOARD_SESSION_A, metrics) == Path("/srv/wt")


def test_git_folder_falls_back_to_the_session_folder() -> None:
    for metrics in (None, StatuslineData(), StatuslineData(worktree_path="rel/wt")):
        assert git_folder(BOARD_SESSION_A, metrics) == BOARD_SESSION_A.cwd


def test_board_sessions_fills_git_from_the_folder() -> None:
    data: BoardData = replace(board_data(), git={BOARD_SESSION_A.cwd: _STATE})
    infos = board_sessions(data, ViewState()).infos
    assert infos[BOARD_SESSION_A.id].git == _STATE
    other = [i for sid, i in infos.items() if sid != BOARD_SESSION_A.id]
    assert all(i.git is None for i in other)
