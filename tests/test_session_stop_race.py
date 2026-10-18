"""A reread by the board between the kill and the stop's final write does not win."""

from pathlib import Path

import pytest

from meute.cli import session_stop
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_refresh import refresh
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.session_state import Exited, SessionState, Unreachable
from meute.tmux.client import Tmux
from meute.tmux.panes import kill_pane
from meute.tmux.parse import PaneId
from test_board_backend import ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportUnusedImport] — fixtures reused


def test_a_reread_right_after_the_kill_still_ends_exited(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "stubborn.sh"
    script.write_text("#!/bin/sh\ntrap '' INT\nsleep 3600\n", encoding="utf-8")
    script.chmod(0o700)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), {"SHELL": str(script)})
    reread: list[SessionState] = []

    def kill_then_board_rereads(tmux: Tmux, pane: PaneId) -> None:
        kill_pane(tmux, pane)
        (row,) = refresh(ctx, env, include_ended=True).sessions
        reread.append(row.session.state)

    monkeypatch.setattr(session_stop, "kill_pane", kill_then_board_rereads)
    stopped = stop_session(ctx, env, session.id, grace=0.2)
    assert reread == [Unreachable()]  # the board saw the pane gone first
    assert stopped.state == Exited(code=None)
