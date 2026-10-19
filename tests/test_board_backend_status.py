"""The backend keeps `@meute_status` up to date, and writes it only when it changes."""

from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.paths import Paths
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
_ENVIRON = {"SHELL": "/bin/sh"}


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


@pytest.fixture
def env(tmux_server: TestServer, tmp_path: Path) -> TmuxEnv:
    return TmuxEnv(tmux=tmux_server.tmux, spec=_SPEC, config_file=tmp_path / "tmux.conf")


def _status(env: TmuxEnv) -> str:
    return env.tmux.run("show-options", "-gv", STATUS_OPTION).strip()


def test_status_follows_the_displayed_session(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path
) -> None:
    _ = ensure_layout(env.tmux, _SPEC)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    show_session(ctx, env, session.id)
    env.tmux.run("set-option", "-g", STATUS_OPTION, "stale")
    assert CliBoardBackend(ctx, env, _ENVIRON).load() is not None
    assert _status(env) == "▶ trial"


def test_status_is_not_rewritten_when_unchanged(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path
) -> None:
    _ = ensure_layout(env.tmux, _SPEC)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    show_session(ctx, env, session.id)
    ticks = iter(range(0, 1000, 10))
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=lambda: float(next(ticks)))
    assert backend.load() is not None
    env.tmux.run("set-option", "-g", STATUS_OPTION, "sentinel")
    assert backend.load() is not None  # reread: same text, so no write
    assert _status(env) == "sentinel"
