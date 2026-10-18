"""The `Outside meute` section of the board."""

from dataclasses import replace
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from meute.core.agents import AgentInfo
from meute.core.board_view import board_lines, entry_line_indexes
from support import board_data


def _agent(name: str, status: str, cwd: str) -> AgentInfo:
    return AgentInfo(pid=1, cwd=cwd, kind="interactive", session_id="x", name=name, status=status)


def test_board_lines_with_outside(snapshot: SnapshotAssertion) -> None:
    data = replace(
        board_data(),
        home=Path("/home/me"),
        outside=(
            _agent("review", "busy", "/home/me/git/meute"),
            _agent("evil\x1b[31m", "idle", "/srv/x"),
        ),
    )
    assert board_lines(data) == snapshot


def test_no_outside_no_section() -> None:
    assert "Outside meute" not in board_lines(board_data())


def test_outside_is_not_selectable() -> None:
    plain = board_data()
    data = replace(plain, outside=(_agent("a", "idle", "/x"),))
    assert entry_line_indexes(data) == entry_line_indexes(plain)
