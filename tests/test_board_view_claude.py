"""The dashboard's Claude launch action."""

from pathlib import Path

from meute.core.board_view import (
    FOOTER,
    LaunchClaude,
    RepoEntry,
    SessionEntry,
    claude_action,
)
from meute.core.project import RepoId
from support import BOARD_REPO_1, board_data


def test_c_on_repo_launches_claude_there() -> None:
    assert claude_action(RepoEntry(repo=BOARD_REPO_1)) == LaunchClaude(
        cwd=BOARD_REPO_1.path, repo_id=RepoId(1)
    )


def test_c_on_session_launches_claude_where_it_runs() -> None:
    data = board_data()
    assert claude_action(SessionEntry(row=data.sessions[0])) == LaunchClaude(
        cwd=data.sessions[0].session.cwd, repo_id=None
    )
    assert claude_action(SessionEntry(row=data.sessions[1])) == LaunchClaude(
        cwd=Path("/srv/work"), repo_id=None
    )


def test_footer_lists_both_launch_keys() -> None:
    assert FOOTER == "↑↓ select · Enter show · c/n new · x stop · ? keys"
