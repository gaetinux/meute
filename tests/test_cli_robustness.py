"""Robustness fixes from the final review of plan 2: cleanup, repair and error wrapping."""

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli import session_launch
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv, open_tmux_env
from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import ShowSession
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.errors import InvalidInput, MeuteError
from meute.core.paths import Paths
from meute.core.session import NewSession, Session, new_session_id
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import ensure_layout, find_layout
from meute.tmux.names import MAIN_SESSION, MAIN_WINDOW, STATUS_OPTION
from meute.tmux.panes import kill_pane, list_panes
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


def test_launch_failure_surfaces_even_when_the_pane_is_already_gone(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_create(_db: Database, new: NewSession) -> Session:
        (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == new.id)
        kill_pane(env.tmux, pane.id)
        message = "recording failed"
        raise InvalidInput(message)

    monkeypatch.setattr(session_launch, "create_session", failing_create)
    with pytest.raises(InvalidInput, match=r"^recording failed$"):
        _ = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)


def test_show_repairs_a_main_area_killed_by_hand(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path
) -> None:
    layout = ensure_layout(env.tmux, _SPEC)
    assert layout.main is not None
    kill_pane(env.tmux, layout.main)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    show_session(ctx, env, session.id)
    (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == session.id)
    assert (pane.session, pane.window) == (MAIN_SESSION, MAIN_WINDOW)
    repaired = find_layout(env.tmux)
    assert repaired is not None
    assert repaired.main == pane.id
    assert env.tmux.run("show-options", "-gv", STATUS_OPTION) == "▶ trial"


@pytest.mark.parametrize("error", [OSError("disk full"), sqlite3.OperationalError("locked")])
def test_perform_wraps_environment_errors(
    ctx: CliContext, env: TmuxEnv, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def failing_show(*_args: object) -> None:
        raise error

    monkeypatch.setattr("meute.cli.board_backend.show_session", failing_show)
    backend = CliBoardBackend(ctx, env, _ENVIRON)
    with pytest.raises(MeuteError) as raised:
        backend.perform(ShowSession(session_id=new_session_id()))
    assert str(raised.value) == str(error)
    assert raised.value.__cause__ is error


def test_unchanged_tmux_conf_keeps_its_inode(ctx: CliContext) -> None:
    first = open_tmux_env(ctx, {}).config_file.stat().st_ino
    assert open_tmux_env(ctx, {}).config_file.stat().st_ino == first
