"""Stopping or closing the displayed pane shows the next live session of the board."""

import stat
from dataclasses import replace
from pathlib import Path

from conftest import Sandbox
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext, open_database
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import CloseOrphan, ShowPane
from meute.core.db.sessions import list_sessions
from meute.core.session import AgentKind, SessionId
from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import displayed_meute_id, ensure_layout
from meute.tmux.names import ID_OPTION
from meute.tmux.panes import set_pane_option
from meute.tmux.parse import PaneId
from support import wait_until
from test_board_backend import ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportUnusedImport] — fixtures reused

_SLEEP = ("sh", "-c", "sleep 3600")
_SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=100,
    board_command=_SLEEP,
    welcome_command=_SLEEP,
    sync_command=("true",),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)


def _tmux(sandbox: Sandbox) -> Tmux:
    # The throw-away server must not read the user's tmux.conf.
    return Tmux(socket=sandbox.tmux_socket, config_file=Path("/dev/null"))


def _new(sandbox: Sandbox, title: str) -> SessionId:
    script = sandbox.root / "shell.sh"
    script.write_text("#!/bin/sh\nexec sleep 3600\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    result = sandbox.run(
        "session", "new", "--kind", "bash", "--cwd", str(folder), "--title", title,
        env={"SHELL": str(script)},
    )  # fmt: skip
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = (s for s in list_sessions(db) if s.title == title)
    return session.id


def _show(sandbox: Sandbox, session_id: str) -> None:
    result = sandbox.run("session", "show", session_id[:8])
    assert result.returncode == 0, result.stderr


def _stop(sandbox: Sandbox, session_id: str) -> None:
    result = sandbox.run("session", "stop", session_id[:8], "--yes")
    assert result.returncode == 0, result.stderr


def test_stopping_the_displayed_session_shows_the_next_one(sandbox: Sandbox) -> None:
    ensure_layout(_tmux(sandbox), _SPEC)
    first, second = _new(sandbox, "alpha"), _new(sandbox, "beta")
    _show(sandbox, first)
    _stop(sandbox, first)
    assert displayed_meute_id(_tmux(sandbox)) == second
    assert _tmux(sandbox).run("show-options", "-gv", "@meute_status") == "▶ beta"


def test_the_next_one_wraps_around_to_the_first(sandbox: Sandbox) -> None:
    ensure_layout(_tmux(sandbox), _SPEC)
    first, second = _new(sandbox, "alpha"), _new(sandbox, "beta")
    _show(sandbox, second)
    _stop(sandbox, second)
    assert displayed_meute_id(_tmux(sandbox)) == first


def test_stopping_a_session_in_the_background_changes_nothing_shown(sandbox: Sandbox) -> None:
    ensure_layout(_tmux(sandbox), _SPEC)
    first, second = _new(sandbox, "alpha"), _new(sandbox, "beta")
    _ = _new(sandbox, "gamma")
    _show(sandbox, first)
    _stop(sandbox, second)
    assert displayed_meute_id(_tmux(sandbox)) == first


def test_closing_the_displayed_orphan_shows_a_live_session(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = ensure_layout(env.tmux, env.spec)
    backend = CliBoardBackend(ctx, env, {"SHELL": "/bin/sh"})
    # The close runs on a connection of its own, to the database of `ctx.paths`.
    with open_database(ctx.paths, ctx.db.clock) as db:
        session = launch_bash(
            replace(ctx, db=db), env, BashLaunch(cwd=tmp_path), {"SHELL": "/bin/sh"}
        )
    orphan = PaneId(
        env.tmux.run(
            "new-window", "-d", "-P", "-F", "#{pane_id}", "-c", str(tmp_path), "-t", "test:",
            "sleep 3600",
        )
    )  # fmt: skip
    set_pane_option(env.tmux, orphan, ID_OPTION, "ghost")
    backend.perform(ShowPane(pane_id=orphan))
    assert displayed_meute_id(env.tmux) == "ghost"
    backend.perform(CloseOrphan(meute_id="ghost", agent=AgentKind.BASH))
    wait_until("the next session shown", lambda: displayed_meute_id(env.tmux) == session.id)
