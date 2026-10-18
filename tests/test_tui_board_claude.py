"""The `c` key of the dashboard."""

from pathlib import Path

from meute.core.board_view import LaunchClaude
from meute.core.project import RepoId
from support import BOARD_REPO_1, board_data
from test_tui_board import FakeBackend, _run  # pyright: ignore[reportPrivateUsage] — reuse the board test helpers


def test_c_launches_claude_on_repo_and_session() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "down", "c", "j", "c")
    assert backend.actions == [
        LaunchClaude(cwd=Path("/srv/work"), repo_id=None),
        LaunchClaude(cwd=BOARD_REPO_1.path, repo_id=RepoId(1)),
    ]


def test_c_while_confirming_a_stop_only_cancels() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "x", "c")
    assert backend.actions == []
