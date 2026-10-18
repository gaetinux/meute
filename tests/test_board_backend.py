"""`CliBoardBackend` against a throw-away tmux server, with a simulated clock."""

from collections.abc import Generator
from pathlib import Path

import pytest

from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.board_view import BoardData, LaunchBash, ShowSession
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.errors import MeuteError
from meute.core.paths import Paths
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.errors import NotInstalled
from meute.tmux.layout import ensure_layout
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
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


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


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


def _loaded(backend: CliBoardBackend) -> BoardData:
    data = backend.load()
    assert data is not None
    return data


def test_first_load_returns_data(ctx: CliContext, env: TmuxEnv, tmp_path: Path) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path, title="trial"), _ENVIRON)
    data = _loaded(CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock()))
    assert [row.session.id for row in data.sessions] == [session.id]
    assert data.sessions[0].has_pane
    assert data.home == Path.home()


def test_unchanged_load_returns_none(ctx: CliContext, env: TmuxEnv) -> None:
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    _loaded(backend)
    clock.now += 1.9
    assert backend.load() is None


def test_load_after_two_seconds_rereads_tmux(ctx: CliContext, env: TmuxEnv, tmp_path: Path) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    clock = _Clock()
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=clock)
    _loaded(backend)
    (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == session.id)
    env.tmux.run("kill-pane", "-t", pane.id)
    clock.now += 1.0
    assert backend.load() is None
    clock.now += 1.0
    assert _loaded(backend).sessions == ()  # the pane vanished: the session ended


def test_load_after_a_write_from_another_connection_rereads(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path
) -> None:
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    _loaded(backend)
    with Database.open(tmp_path / "meute.db", busy_timeout_ms=1000, clock=lambda: FIXED) as other:
        _ = create_project(other, "elsewhere")
    assert backend.load() is not None
    assert backend.load() is None


def test_load_after_an_action_rereads(ctx: CliContext, env: TmuxEnv, tmp_path: Path) -> None:
    ensure_layout(env.tmux, _SPEC)
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    assert not _loaded(backend).sessions[0].displayed
    backend.perform(ShowSession(session_id=session.id))
    assert _loaded(backend).sessions[0].displayed


def test_launch_bash_shows_the_new_session(ctx: CliContext, env: TmuxEnv, tmp_path: Path) -> None:
    ensure_layout(env.tmux, _SPEC)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    backend.perform(LaunchBash(cwd=tmp_path, repo_id=None))
    (row,) = _loaded(backend).sessions
    (pane,) = (p for p in list_panes(env.tmux) if p.meute_id == row.session.id)
    assert pane.session == MAIN_SESSION


def test_tmux_error_becomes_meute_error(
    ctx: CliContext, env: TmuxEnv, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = launch_bash(ctx, env, BashLaunch(cwd=tmp_path), _ENVIRON)
    backend = CliBoardBackend(ctx, env, _ENVIRON, monotonic=_Clock())
    monkeypatch.setenv("PATH", "")
    with pytest.raises(MeuteError) as loading:
        _ = backend.load()
    with pytest.raises(MeuteError) as showing:
        backend.perform(ShowSession(session_id=session.id))
    assert str(loading.value) == str(showing.value) == str(NotInstalled())
