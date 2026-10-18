"""Tests of the dashboard view model."""

from datetime import UTC, datetime
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from meute.core.board_view import (
    BoardData,
    LaunchBash,
    RepoEntry,
    SessionEntry,
    SessionRow,
    ShowSession,
    board_entries,
    board_lines,
    confirm_stop_text,
    enter_action,
    entry_key,
    error_text,
    new_action,
    stop_target,
)
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Running

_AT = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
_HOME = Path("/home/me")
_ID_A = SessionId("11111111-1111-4111-8111-111111111111")
_ID_B = SessionId("22222222-2222-4222-8222-222222222222")


def _session(
    session_id: SessionId, title: str, cwd: Path, repo_id: RepoId | None, *, exited: bool
) -> Session:
    return Session(
        id=session_id,
        agent=AgentKind.BASH,
        title=title,
        project_id=None,
        repo_id=repo_id,
        task_id=None,
        cwd=cwd,
        state=Exited(code=2) if exited else Running(),
        last_activity_at=_AT,
        created_at=_AT,
        ended_at=None,
    )


def _repo(repo_id: int, name: str, kind: str | None) -> Repo:
    return Repo(
        id=RepoId(repo_id), path=_HOME / "git" / name, name=name, kind=kind, discovered_at=_AT
    )


_SESSION_A = _session(_ID_A, "build", _HOME / "git" / "meute", RepoId(1), exited=False)
_SESSION_B = _session(_ID_B, "tests", Path("/srv/work"), None, exited=True)
_REPO_1 = _repo(1, "meute", "rust")
_REPO_2 = _repo(2, "notes", None)


def _data() -> BoardData:
    return BoardData(
        sessions=(
            SessionRow(session=_SESSION_A, has_pane=True, displayed=True),
            SessionRow(session=_SESSION_B, has_pane=True, displayed=False),
        ),
        repos=(_REPO_1, _REPO_2),
        orphans=("%7",),
        home=_HOME,
    )


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
