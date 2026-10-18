"""Dead panes without an exit status: killed by a signal, or not settled yet (R1)."""

import os
import signal
from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.session_refresh import apply_refresh, dead_pane_settled, refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, get_session
from meute.core.paths import Paths
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Running
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.names import ID_OPTION, MAIN_SESSION
from meute.tmux.panes import set_pane_option
from meute.tmux.parse import PaneId, PaneInfo
from support import wait_until
from tmux_support import TestServer

ID_A = SessionId("11111111-1111-4111-8111-111111111111")


def _create(db: Database) -> None:
    create_session(
        db,
        NewSession(id=ID_A, agent=AgentKind.CLAUDE, title="t", cwd=Path("/srv"), state=Running()),
    )


def _dead_pane() -> PaneInfo:
    return PaneInfo(
        id=PaneId("%1"),
        session=MAIN_SESSION,
        window="w",
        meute_id=ID_A,
        role=None,
        dead=True,
        dead_status=None,
        width=80,
    )


@pytest.mark.parametrize(
    ("output", "now", "settled"),
    [
        ("15 1000", 1001.0, True),  # killed by a signal: known at once
        (" 1000", 1001.0, False),  # no signal, died 1 s ago: the status may still come
        (" 1000", 1010.0, True),  # no signal, died long ago: tmux lost the status
        (" 1000", 999.0, False),  # clock skew: still recent
        ("garbage", 1000.0, True),
        ("", 1000.0, True),
    ],
)
def test_dead_pane_settled(output: str, now: float, settled: bool) -> None:  # noqa: FBT001 — parameter
    assert dead_pane_settled(output, now) is settled


def test_unsettled_pane_keeps_the_session_alive(db: Database) -> None:
    _create(db)
    apply_refresh(db, [_dead_pane()], unsettled=frozenset({PaneId("%1")}))
    assert get_session(db, ID_A).state == Running()


def test_settled_pane_without_status_exits_without_code(db: Database) -> None:
    _create(db)
    apply_refresh(db, [_dead_pane()])
    assert get_session(db, ID_A).state == Exited(code=None)


def test_pane_killed_by_a_signal_exits_at_once(
    db: Database, tmux_server: TestServer, tmp_path: Path
) -> None:
    tmux = tmux_server.tmux
    tmux.run("set-option", "-g", "remain-on-exit", "on")
    _create(db)
    pane = PaneId(
        tmux.run("new-window", "-d", "-P", "-F", "#{pane_id}", "-t", "test:", "sleep 300")
    )
    set_pane_option(tmux, pane, ID_OPTION, ID_A)
    pid = int(tmux.run("display-message", "-p", "-t", pane, "#{pane_pid}"))
    os.kill(pid, signal.SIGTERM)
    wait_until(
        "pane dead", lambda: tmux.run("display-message", "-p", "-t", pane, "#{pane_dead}") == "1"
    )
    spec = LayoutSpec(
        board_width=30,
        narrow_threshold=100,
        board_command=("b",),
        welcome_command=("w",),
        sync_command=("s",),
        keys=Keys(focus_board="a", focus_main="b"),
    )
    ctx = CliContext(
        db=db,
        now=db.now(),
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=Config(),
        paths=Paths.from_roots(config_home=tmp_path, data_home=tmp_path, state_home=tmp_path),
    )
    refresh(ctx, TmuxEnv(tmux=tmux, spec=spec, config_file=tmp_path / "c"))
    assert get_session(db, ID_A).state == Exited(code=None)
