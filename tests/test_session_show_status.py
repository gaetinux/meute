"""`show_session` writes the full status text: title, attention count and 5 h quota."""

from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.samples import record_quota
from meute.core.db.sessions import set_session_state
from meute.core.paths import Paths
from meute.core.session_state import PermissionRequested
from meute.core.statusline import StatuslineData
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import ensure_layout
from meute.tmux.names import STATUS_OPTION
from support import FIXED
from tmux_support import TestServer

_SLEEP = ("sh", "-c", "sleep 3600")
_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=100,
    board_command=_SLEEP,
    welcome_command=_SLEEP,
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)


@pytest.fixture
def ctx(tmp_path: Path) -> Generator[CliContext]:
    with Database.open(tmp_path / "meute.db", busy_timeout_ms=1000, clock=lambda: FIXED) as db:
        yield CliContext(
            db=db,
            now=FIXED,
            actor=Actor(author=Author.USER, channel=Channel.CLI),
            config=Config(),
            paths=Paths.from_env({"XDG_STATE_HOME": str(tmp_path)}, home=tmp_path),
        )


def test_show_writes_title_attention_and_quota(
    ctx: CliContext, tmux_server: TestServer, tmp_path: Path
) -> None:
    env = TmuxEnv(tmux=tmux_server.tmux, spec=_SPEC, config_file=tmp_path / "tmux.conf")
    _ = ensure_layout(env.tmux, _SPEC)
    environ = {"SHELL": "/bin/sh"}
    shown = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="alpha"), environ)
    asking = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="beta"), environ)
    _ = set_session_state(ctx.db, asking.id, PermissionRequested())
    _ = record_quota(ctx.db, StatuslineData(five_hour_pct=42.0))
    show_session(ctx, env, shown.id)
    status = env.tmux.run("show-options", "-gv", STATUS_OPTION).strip()
    assert status == "▶ alpha · 1 need attention · 5h 42%"
