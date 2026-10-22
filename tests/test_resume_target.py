"""`r` on the board: which session it resumes, or why it refuses."""

from dataclasses import replace
from pathlib import Path

from meute.core.board_view import (
    RepoEntry,
    ResumeSession,
    SessionEntry,
    SessionRow,
    resume_target,
    resuming_text,
)
from meute.core.claude_session import ClaudeDetails
from meute.core.session import AgentKind, Session
from meute.core.session_state import Exited, Running, Unreachable
from support import BOARD_ID_A, BOARD_REPO_1, board_session

_CWD = Path("/srv/work")


def _claude(title: str = "work", *, exited: bool = True) -> Session:
    base = board_session(BOARD_ID_A, title, _CWD, None, exited=exited)
    return replace(base, agent=AgentKind.CLAUDE)


def _entry(session: Session) -> SessionEntry:
    return SessionEntry(row=SessionRow(session=session, has_pane=False, displayed=False))


_KNOWN = {BOARD_ID_A: ClaudeDetails(native_id="abc")}


def test_an_ended_claude_session_with_a_native_id_is_the_target() -> None:
    session = _claude()
    assert resume_target(_entry(session), _KNOWN) == session


def test_an_unreachable_claude_session_is_the_target() -> None:
    session = replace(_claude(), state=Unreachable())
    assert resume_target(_entry(session), _KNOWN) == session


def test_a_bash_session_does_not_resume() -> None:
    session = board_session(BOARD_ID_A, "sh", _CWD, None, exited=True)
    assert resume_target(_entry(session), _KNOWN) == "only Claude sessions resume"


def test_a_repository_does_not_resume() -> None:
    assert resume_target(RepoEntry(repo=BOARD_REPO_1), _KNOWN) == "only Claude sessions resume"


def test_a_live_session_is_still_running() -> None:
    session = replace(_claude("a\x1bb"), state=Running())
    assert resume_target(_entry(session), _KNOWN) == '"a�b" is still running'


def test_without_a_native_id_the_refusal_says_so() -> None:
    expected = '"work" cannot be resumed: Claude never confirmed its id'
    assert resume_target(_entry(_claude()), {}) == expected
    assert resume_target(_entry(_claude()), {BOARD_ID_A: ClaudeDetails()}) == expected


def test_the_exited_state_is_what_ends_a_session() -> None:
    assert isinstance(_claude().state, Exited)


def test_resuming_text_names_the_session() -> None:
    assert resuming_text("a\x1bb") == 'Resuming "a�b"…'


def test_resume_session_names_the_session() -> None:
    assert ResumeSession(session_id=BOARD_ID_A).session_id == BOARD_ID_A
