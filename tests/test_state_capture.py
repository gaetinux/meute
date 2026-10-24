"""Capturing the board's live sessions as the entries of a saved state, in the board order."""

from dataclasses import replace
from pathlib import Path

from meute.core.board_sessions import board_session_order
from meute.core.board_view import SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.project import RepoId
from meute.core.saved_state import SavedSession
from meute.core.session import AgentKind, SessionId
from meute.core.state_capture import capture
from meute.core.task import TaskId
from support import (
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    BOARD_REPO_1,
    BOARD_SESSION_A,
    BOARD_SESSION_B,
    board_data,
    board_session,
)

_ID_C = SessionId("33333333-3333-4333-8333-333333333333")


def test_capture_follows_the_given_order_and_keeps_displayed() -> None:
    sessions = capture(board_data(), (BOARD_ID_B, BOARD_ID_A))
    assert sessions == (
        SavedSession(
            session_id=BOARD_ID_B,
            agent=AgentKind.BASH,
            cwd=Path("/srv/work"),
            native_id=None,
            title="tests",
            task_id=None,
            repo_id=None,
            displayed=False,
        ),
        SavedSession(
            session_id=BOARD_ID_A,
            agent=AgentKind.BASH,
            cwd=BOARD_HOME / "git" / "meute",
            native_id=None,
            title="build",
            task_id=None,
            repo_id=None,
            displayed=True,
        ),
    )


def test_capture_leaves_out_the_ended_sessions() -> None:
    ended = board_session(_ID_C, "old", Path("/srv/old"), None, exited=True)
    data = replace(
        board_data(),
        sessions=(
            *board_data().sessions,
            SessionRow(session=ended, has_pane=True, displayed=False),
        ),
    )
    assert [s.session_id for s in capture(data, (_ID_C, BOARD_ID_A, BOARD_ID_B))] == [
        BOARD_ID_A,
        BOARD_ID_B,
    ]


def test_capture_takes_the_native_id_task_and_repo_of_a_claude_session() -> None:
    claude = replace(BOARD_SESSION_A, agent=AgentKind.CLAUDE, task_id=TaskId(4), repo_id=RepoId(1))
    data = replace(
        board_data(),
        sessions=(SessionRow(session=claude, has_pane=True, displayed=True),),
        details={BOARD_ID_A: ClaudeDetails(native_id="native-1")},
    )
    (saved,) = capture(data, (BOARD_ID_A,))
    assert (saved.agent, saved.native_id, saved.task_id, saved.repo_id) == (
        AgentKind.CLAUDE,
        "native-1",
        TaskId(4),
        RepoId(1),
    )


def test_capture_gives_no_native_id_to_a_session_without_details() -> None:
    data = replace(board_data(), details={BOARD_ID_B: ClaudeDetails(native_id="other")})
    (saved,) = capture(data, (BOARD_ID_A,))
    assert saved.native_id is None


def test_capture_skips_ids_the_data_lacks() -> None:
    assert capture(board_data(), (_ID_C,)) == ()


def test_board_session_order_is_the_order_of_the_board_groups() -> None:
    in_repo = replace(BOARD_SESSION_A, repo_id=BOARD_REPO_1.id)
    data = replace(
        board_data(),
        sessions=(
            SessionRow(session=BOARD_SESSION_B, has_pane=True, displayed=False),
            SessionRow(session=in_repo, has_pane=True, displayed=True),
        ),
    )
    # "meute" (the repository's group) comes before "Other", whatever the data order.
    assert board_session_order(data) == (BOARD_ID_A, BOARD_ID_B)


def test_board_session_order_leaves_out_the_recently_ended_sessions() -> None:
    ended = board_session(_ID_C, "old", Path("/srv/old"), None, exited=True)
    data = replace(
        board_data(), ended=(SessionRow(session=ended, has_pane=False, displayed=False),)
    )
    assert _ID_C not in board_session_order(data)
