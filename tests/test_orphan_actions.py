"""Showing, adopting and closing an orphan pane on a throw-away tmux server."""

import sqlite3
from pathlib import Path

import pytest

from meute.cli import orphan_actions
from meute.cli.board_backend import CliBoardBackend
from meute.cli.context import CliContext, open_database
from meute.cli.orphan_actions import adopt_orphan, close_orphan, show_orphan
from meute.cli.session_refresh import refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import AdoptOrphan, CloseOrphan, ShowPane
from meute.core.db.connection import Database
from meute.core.db.sessions import get_session, list_sessions
from meute.core.errors import InvalidInput
from meute.core.orphans import Orphan
from meute.core.session import AgentKind, NewSession, Session, new_session_id
from meute.core.session_state import Running
from meute.tmux.layout import ensure_layout, find_layout
from meute.tmux.names import ID_OPTION
from meute.tmux.panes import list_panes, set_pane_option
from meute.tmux.parse import PaneId
from support import wait_until
from test_board_backend import ctx, env  # noqa: F401 — fixtures reused  # pyright: ignore[reportUnusedImport] — fixtures reused
from tmux_support import TestServer


def _orphan_pane(tmux_env: TmuxEnv, folder: Path, meute_id: str) -> Orphan:
    tmux = tmux_env.tmux
    pane = PaneId(
        tmux.run(
            "new-window", "-d", "-P", "-F", "#{pane_id}", "-c", str(folder), "-t", "test:",
            "sleep 3600",
        )
    )  # fmt: skip
    set_pane_option(tmux, pane, ID_OPTION, meute_id)
    wait_until(
        "command started",
        lambda: tmux.run("display-message", "-p", "-t", pane, "#{pane_current_command}") == "sleep",
    )
    return Orphan(meute_id=meute_id, pane_id=pane, command="sleep", cwd=str(folder), dead=False)


def test_adoption_creates_the_session_and_the_next_read_lists_it_live(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    orphan = _orphan_pane(env, tmp_path, str(new_session_id()))
    session = adopt_orphan(ctx, orphan)
    assert session is not None
    assert get_session(ctx.db, session.id).cwd == tmp_path
    snapshot = refresh(ctx, env)
    assert snapshot.orphans == ()
    (row,) = snapshot.sessions
    assert (row.session.id, row.has_pane, row.session.state) == (session.id, True, Running())
    assert row.session.agent is AgentKind.BASH


def test_a_second_adoption_returns_none(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    orphan = _orphan_pane(env, tmp_path, str(new_session_id()))
    assert adopt_orphan(ctx, orphan) is not None
    assert adopt_orphan(ctx, orphan) is None
    assert len(list_sessions(ctx.db)) == 1


def test_a_refused_adoption_is_an_invalid_input_and_writes_nothing(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    orphan = _orphan_pane(env, tmp_path, "x;y")
    with pytest.raises(InvalidInput, match="not a meute id"):
        _ = adopt_orphan(ctx, orphan)
    assert list_sessions(ctx.db, include_ended=True) == []


def test_closing_kills_the_pane_and_writes_nothing(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    orphan = _orphan_pane(env, tmp_path, "x;y")  # even an id that is not one
    close_orphan(env, orphan.meute_id, AgentKind.BASH)
    assert all(pane.id != orphan.pane_id for pane in list_panes(env.tmux))
    assert list_sessions(ctx.db, include_ended=True) == []


def test_closing_a_pane_already_gone_does_nothing(env: TmuxEnv) -> None:  # noqa: F811 — fixture
    close_orphan(env, "ghost", AgentKind.CLAUDE)


def test_show_puts_the_orphan_in_the_main_area(
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = ensure_layout(env.tmux, env.spec)
    orphan = _orphan_pane(env, tmp_path, "ghost")
    show_orphan(env, orphan.pane_id)
    layout = find_layout(env.tmux)
    assert layout is not None
    assert layout.main == orphan.pane_id


def test_show_refuses_a_dead_pane(
    env: TmuxEnv,  # noqa: F811 — fixture
    tmux_server: TestServer,
    tmp_path: Path,
) -> None:
    _ = ensure_layout(env.tmux, env.spec)
    orphan = _orphan_pane(env, tmp_path, "ghost")
    env.tmux.run("set-option", "-p", "-t", orphan.pane_id, "remain-on-exit", "on")
    env.tmux.run("respawn-pane", "-k", "-t", orphan.pane_id, "true")
    wait_until(
        "pane dead",
        lambda: any(p.id == orphan.pane_id and p.dead for p in list_panes(tmux_server.tmux)),
    )
    with pytest.raises(InvalidInput, match="dead pane: nothing to show"):
        show_orphan(env, orphan.pane_id)


def test_show_of_a_vanished_pane_is_an_invalid_input(env: TmuxEnv) -> None:  # noqa: F811 — fixture
    _ = ensure_layout(env.tmux, env.spec)
    with pytest.raises(InvalidInput, match="pane is gone"):
        show_orphan(env, "%999")


def test_the_backend_routes_the_three_actions(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
) -> None:
    _ = ensure_layout(env.tmux, env.spec)
    backend = CliBoardBackend(ctx, env, {"SHELL": "/bin/sh"})
    orphan = _orphan_pane(env, tmp_path, str(new_session_id()))
    backend.perform(ShowPane(pane_id=orphan.pane_id))
    backend.perform(AdoptOrphan(orphan=orphan))
    with open_database(ctx.paths, ctx.db.clock) as db:  # the adoption wrote on its own connection
        assert [s.id for s in list_sessions(db)] == [orphan.meute_id]
    backend.perform(CloseOrphan(meute_id=orphan.meute_id, agent=AgentKind.BASH))
    assert all(pane.id != orphan.pane_id for pane in list_panes(env.tmux))


def _integrity_failure(_db: Database, _new: NewSession) -> Session:
    message = "FOREIGN KEY constraint failed"
    raise sqlite3.IntegrityError(message)


def test_an_integrity_failure_without_the_row_is_not_swallowed(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan = _orphan_pane(env, tmp_path, str(new_session_id()))
    monkeypatch.setattr(orphan_actions, "create_session", _integrity_failure)
    with pytest.raises(sqlite3.IntegrityError):
        _ = adopt_orphan(ctx, orphan)


def test_an_integrity_failure_with_the_row_present_means_a_lost_race(
    ctx: CliContext,  # noqa: F811 — fixture
    env: TmuxEnv,  # noqa: F811 — fixture
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orphan = _orphan_pane(env, tmp_path, str(new_session_id()))
    real = orphan_actions.create_session

    def lose_the_race(db: Database, new: NewSession) -> Session:
        _ = real(db, new)  # the other adoption wrote first
        return _integrity_failure(db, new)

    monkeypatch.setattr(orphan_actions, "create_session", lose_the_race)
    assert adopt_orphan(ctx, orphan) is None
