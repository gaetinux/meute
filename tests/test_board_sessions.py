"""Tests of the board's Sessions model: from `BoardData` to lines, entries and groups."""

from dataclasses import replace
from datetime import timedelta

from meute.core.board_sessions import (
    BoardSessions,
    board_sessions,
    line_entry,
    line_group,
    line_info,
    risky_mode_span,
)
from meute.core.board_view import NO_SESSIONS, BoardData, RepoEntry, SessionEntry, SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.project import ProjectId, RepoId
from meute.core.session_state import Exited
from meute.core.sessions_view import HeaderLine, InfoLine, RepoLine, SessionLine, ViewState
from meute.core.statusline import StatuslineData
from support import (
    BOARD_AT,
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    BOARD_REPO_1,
    BOARD_REPO_2,
    board_data,
    board_session,
)


def _index(model: BoardSessions, kind: type, n: int = 0) -> int:
    return [i for i, line in enumerate(model.view.lines) if isinstance(line, kind)][n]


def test_sessions_are_grouped_by_project_then_repo() -> None:
    planned = replace(
        board_session(BOARD_ID_A, "build", BOARD_HOME, RepoId(1), exited=False),
        project_id=ProjectId(3),
    )
    in_repo = board_session(BOARD_ID_B, "tests", BOARD_HOME, RepoId(2), exited=False)
    data = BoardData(
        sessions=(
            SessionRow(session=planned, has_pane=True, displayed=False),
            SessionRow(session=in_repo, has_pane=True, displayed=False),
        ),
        repos=(BOARD_REPO_1, BOARD_REPO_2),
        orphans=(),
        home=BOARD_HOME,
        projects={ProjectId(3): "Plan"},
        now=BOARD_AT,
    )
    model = board_sessions(data, ViewState())
    headers = [line.group for line in model.view.lines if isinstance(line, HeaderLine)]
    assert headers == ["notes", "Plan"]
    assert {info.group for info in model.infos.values()} == {"Plan", "notes"}


def test_details_and_metrics_reach_the_lines() -> None:
    data = replace(
        board_data(),
        details={BOARD_ID_A: ClaudeDetails(permission_mode="plan")},
        metrics={BOARD_ID_A: StatuslineData(context_pct=42.0)},
        now=BOARD_AT + timedelta(minutes=5),
    )
    model = board_sessions(data, ViewState())
    line = model.view.lines[_index(model, SessionLine)]
    assert isinstance(line, SessionLine)
    assert line.text == "▶  build  running  5m  42%  [plan]"


def test_without_a_clock_ages_count_from_the_latest_activity() -> None:
    model = board_sessions(board_data(), ViewState())
    line = model.view.lines[_index(model, SessionLine)]
    assert isinstance(line, SessionLine)
    assert line.text == "▶  build  running  now"


def test_no_sessions_says_how_to_start_one() -> None:
    data = BoardData(sessions=(), repos=(BOARD_REPO_1,), orphans=(), home=None)
    model = board_sessions(data, ViewState())
    assert model.view.lines[0] == InfoLine(NO_SESSIONS)
    assert isinstance(model.view.lines[-1], RepoLine)


def test_line_entry_maps_sessions_and_repos_only() -> None:
    data = board_data()
    model = board_sessions(data, ViewState())
    session = _index(model, SessionLine)
    repo = _index(model, RepoLine)
    assert line_entry(model, session) == SessionEntry(row=data.sessions[0])
    assert line_entry(model, repo) == RepoEntry(repo=BOARD_REPO_1)
    assert line_entry(model, _index(model, HeaderLine)) is None
    assert line_entry(model, _index(model, InfoLine)) is None
    assert line_entry(model, -1) is None
    assert line_entry(model, len(model.view.lines)) is None


def test_line_group_of_a_session_and_of_a_header() -> None:
    model = board_sessions(board_data(), ViewState())
    assert line_group(model, _index(model, SessionLine)) == "Other"
    assert line_group(model, _index(model, HeaderLine)) == "Other"
    assert line_group(model, _index(model, RepoLine)) is None
    assert line_group(model, -1) is None


def test_line_info_only_for_sessions() -> None:
    data = board_data()
    model = board_sessions(data, ViewState())
    info = line_info(model, _index(model, SessionLine, 1))
    assert info is not None
    assert info.row == data.sessions[1]
    assert line_info(model, _index(model, RepoLine)) is None
    assert line_info(model, -1) is None


def test_risky_modes_are_spanned_and_others_are_not() -> None:
    for mode, risky in (
        ("auto", True),
        ("bypassPermissions", True),
        ("dontAsk", True),
        ("plan", False),
        ("manual", False),
        ("acceptEdits", False),
    ):
        data = replace(board_data(), details={BOARD_ID_A: ClaudeDetails(permission_mode=mode)})
        model = board_sessions(data, ViewState())
        index = _index(model, SessionLine)
        text = model.view.lines[index].text
        span = risky_mode_span(model, index)
        if risky:
            assert span is not None
            assert text[span[0] : span[1]] == f"[{mode}]"
        else:
            assert span is None
    assert risky_mode_span(model, _index(model, RepoLine)) is None


def test_ended_sessions_count_in_their_group() -> None:
    ended = replace(board_data().sessions[1].session, state=Exited(code=0))
    data = replace(
        board_data(),
        sessions=(
            board_data().sessions[0],
            SessionRow(session=ended, has_pane=True, displayed=False),
        ),
    )
    model = board_sessions(data, ViewState())
    assert InfoLine("1 ended (e to show)") in model.view.lines
    shown = board_sessions(data, ViewState(show_ended=True))
    assert line_info(shown, _index(shown, SessionLine, 1)) is not None


def test_recently_ended_sessions_show_only_with_e() -> None:
    gone = replace(board_data().sessions[1].session, state=Exited(code=0))
    row = SessionRow(session=gone, has_pane=False, displayed=False)
    data = replace(board_data(), sessions=board_data().sessions[:1], ended=(row,))
    hidden = board_sessions(data, ViewState())
    assert InfoLine("1 ended (e to show)") in hidden.view.lines
    lines = range(len(hidden.view.lines))
    assert row not in [info.row for i in lines if (info := line_info(hidden, i)) is not None]
    shown = board_sessions(data, ViewState(show_ended=True))
    info = line_info(shown, _index(shown, SessionLine, 1))
    assert info is not None
    assert info.row == row
