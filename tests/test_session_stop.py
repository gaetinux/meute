"""`stop_session` against a throw-away tmux server."""

from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_stop import stop_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.paths import Paths
from meute.core.session_state import Exited
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.panes import list_panes
from support import FIXED
from tmux_support import TestServer


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    with Database.in_memory(clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
        )


def test_shell_ignoring_sigint_is_killed_after_the_grace(
    ctx: CliContext, tmux_server: TestServer, tmp_path: Path
) -> None:
    spec = LayoutSpec(
        board_width=60,
        narrow_threshold=100,
        board_command=("true",),
        welcome_command=("true",),
        sync_command=("true",),
        keys=Keys(focus_board="M-p", focus_main="M-o"),
    )
    env = TmuxEnv(tmux=tmux_server.tmux, spec=spec, config_file=tmp_path / "tmux.conf")
    script = tmp_path / "stubborn.sh"
    script.write_text("#!/bin/sh\ntrap '' INT\nsleep 3600\n", encoding="utf-8")
    script.chmod(0o700)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), {"SHELL": str(script)})
    stopped = stop_session(ctx, env, session.id, grace=0.2)
    assert stopped.state == Exited(code=None)
    assert all(pane.meute_id != session.id for pane in list_panes(env.tmux))
