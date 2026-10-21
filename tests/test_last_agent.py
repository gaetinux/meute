"""What `n` launches: the last session type of a repository."""

from dataclasses import replace
from pathlib import Path

from meute.core.board_actions import LaunchBash, LaunchClaude
from meute.core.board_view import RepoEntry, SessionEntry, SessionRow, new_action
from meute.core.last_agent import last_agent
from meute.core.project import RepoId
from meute.core.session import AgentKind
from support import BOARD_ID_A, BOARD_ID_B, BOARD_REPO_1, BOARD_REPO_2, board_data, board_session

_REPO = RepoId(1)


def _row(agent: AgentKind, repo_id: RepoId | None, *, late: int, other: bool = False) -> SessionRow:
    base = board_session(BOARD_ID_A, "t", Path("/w/x"), repo_id, exited=False)
    created = base.created_at.replace(minute=late)
    session = replace(base, agent=agent, created_at=created)
    if other:
        session = replace(session, id=BOARD_ID_B)
    return SessionRow(session=session, has_pane=True, displayed=False)


def test_the_database_has_priority_over_the_board_sessions() -> None:
    data = replace(
        board_data(),
        sessions=(_row(AgentKind.CLAUDE, _REPO, late=5),),
        last_agents={_REPO: AgentKind.BASH},
    )
    assert last_agent(data, _REPO, None) is AgentKind.BASH


def test_without_the_database_the_latest_board_session_decides() -> None:
    data = replace(
        board_data(),
        sessions=(_row(AgentKind.CLAUDE, _REPO, late=5),),
        ended=(_row(AgentKind.BASH, _REPO, late=9, other=True),),
    )
    assert last_agent(data, _REPO, None) is AgentKind.BASH


def test_a_session_of_another_repository_does_not_count() -> None:
    data = replace(board_data(), sessions=(_row(AgentKind.BASH, RepoId(2), late=5),))
    assert last_agent(data, _REPO, None) is AgentKind.CLAUDE


def test_a_repository_without_session_gets_claude() -> None:
    assert last_agent(board_data(), _REPO, AgentKind.BASH) is AgentKind.CLAUDE


def test_without_a_repository_the_session_relaunches_its_own_type() -> None:
    assert last_agent(board_data(), None, AgentKind.BASH) is AgentKind.BASH
    assert last_agent(board_data(), None, None) is AgentKind.CLAUDE


def test_new_on_a_repository_without_session_launches_claude() -> None:
    assert new_action(RepoEntry(repo=BOARD_REPO_2), board_data()) == LaunchClaude(
        cwd=BOARD_REPO_2.path, repo_id=RepoId(2)
    )


def test_new_on_a_bash_session_follows_the_repository_last_type() -> None:
    row = _row(AgentKind.BASH, _REPO, late=1)
    data = replace(board_data(), sessions=(row,), last_agents={_REPO: AgentKind.CLAUDE})
    assert new_action(SessionEntry(row=row), data) == LaunchClaude(cwd=Path("/w/x"), repo_id=_REPO)


def test_new_on_a_repository_launches_its_last_type() -> None:
    data = replace(board_data(), last_agents={BOARD_REPO_1.id: AgentKind.BASH})
    assert new_action(RepoEntry(repo=BOARD_REPO_1), data) == LaunchBash(
        cwd=BOARD_REPO_1.path, repo_id=BOARD_REPO_1.id
    )


def test_the_launch_actions_have_optional_fields() -> None:
    assert LaunchBash(cwd=Path("/w"), repo_id=None).title is None
    claude = LaunchClaude(cwd=Path("/w"), repo_id=None)
    assert (claude.title, claude.task_id, claude.permission_mode) == (None, None, None)
