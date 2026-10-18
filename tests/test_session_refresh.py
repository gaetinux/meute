"""Reconciliation of the recorded sessions with the panes tmux reports."""

from pathlib import Path

import pytest

from meute.cli.context import CliContext
from meute.cli.session_refresh import apply_refresh, refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, get_session, list_sessions
from meute.core.paths import Paths
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Running, Unreachable
from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.errors import NotInstalled
from meute.tmux.names import BG_SESSION, MAIN_SESSION
from meute.tmux.parse import PaneId, PaneInfo

ID_A = SessionId("11111111-1111-4111-8111-111111111111")
ID_B = SessionId("22222222-2222-4222-8222-222222222222")


def _pane(
    session: str, meute_id: str | None, *, dead: bool = False, status: int | None = None
) -> PaneInfo:
    return PaneInfo(
        id=PaneId("%1"),
        session=session,
        window="w",
        meute_id=meute_id,
        role=None,
        dead=dead,
        dead_status=status,
        width=80,
    )


def _create(db: Database, session_id: SessionId) -> None:
    create_session(
        db,
        NewSession(
            id=session_id, agent=AgentKind.BASH, title="t", cwd=Path("/srv"), state=Running()
        ),
    )


def test_pane_in_meute_session_is_displayed(db: Database) -> None:
    _create(db, ID_A)
    _create(db, ID_B)
    snapshot = apply_refresh(db, [_pane(MAIN_SESSION, ID_A), _pane(BG_SESSION, ID_B)])
    assert [(r.session.id, r.has_pane, r.displayed) for r in snapshot.sessions] == [
        (ID_A, True, True),
        (ID_B, True, False),
    ]


def test_ended_session_with_dead_pane_is_listed(db: Database) -> None:
    _create(db, ID_A)
    snapshot = apply_refresh(db, [_pane(BG_SESSION, ID_A, dead=True, status=7)])
    (row,) = snapshot.sessions
    assert (row.session.state, row.has_pane) == (Exited(code=7), True)


def test_ended_session_without_pane_is_hidden(db: Database) -> None:
    _create(db, ID_A)
    snapshot = apply_refresh(db, [])
    assert snapshot.sessions == ()
    assert get_session(db, ID_A).state == Unreachable()


def test_ended_session_without_pane_is_kept_on_request(db: Database) -> None:
    _create(db, ID_A)
    snapshot = apply_refresh(db, [], include_ended=True)
    (row,) = snapshot.sessions
    assert (row.session.id, row.has_pane) == (ID_A, False)


def test_reconciled_states_are_written(db: Database) -> None:
    _create(db, ID_A)
    _create(db, ID_B)
    apply_refresh(db, [_pane(BG_SESSION, ID_A, dead=True, status=3), _pane(BG_SESSION, None)])
    assert get_session(db, ID_A).state == Exited(code=3)
    assert get_session(db, ID_B).state == Unreachable()


def test_orphans_are_reported(db: Database) -> None:
    snapshot = apply_refresh(db, [_pane(BG_SESSION, "unknown-id")])
    assert snapshot.orphans == ("unknown-id",)


def test_refresh_writes_nothing_when_tmux_fails(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(db, ID_A)
    monkeypatch.setenv("PATH", "")
    ctx = CliContext(
        db=db,
        now=db.now(),
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=Config(),
        paths=Paths.from_roots(config_home=tmp_path, data_home=tmp_path, state_home=tmp_path),
    )
    spec = LayoutSpec(
        board_width=30,
        narrow_threshold=100,
        board_command=("b",),
        welcome_command=("w",),
        sync_command=("s",),
        keys=Keys(focus_board="a", focus_main="b"),
    )
    env = TmuxEnv(tmux=Tmux(socket="meute-test-none"), spec=spec, config_file=tmp_path / "c")
    with pytest.raises(NotInstalled):
        refresh(ctx, env)
    assert get_session(db, ID_A).state == Running()


def test_session_created_after_the_snapshot_stays_running(db: Database) -> None:
    sessions = list_sessions(db, include_ended=True)
    panes: list[PaneInfo] = []  # read before the session below got its pane
    _create(db, ID_A)
    apply_refresh(db, panes, sessions=sessions)
    assert get_session(db, ID_A).state == Running()
