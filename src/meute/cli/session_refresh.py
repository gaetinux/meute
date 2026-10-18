"""Reading the sessions: tmux is observed, the database is reconciled, then the rows are built."""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import SessionRow
from meute.core.db.connection import Database
from meute.core.db.sessions import list_sessions, set_session_state
from meute.core.reconcile import PaneObservation, first_by_id, reconcile
from meute.core.session import Session
from meute.core.session_state import is_live
from meute.tmux.client import Tmux
from meute.tmux.errors import CommandFailed
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
from meute.tmux.parse import PaneId, PaneInfo

_DEAD_FORMAT = "#{pane_dead_signal} #{pane_dead_time}"
_SETTLE_SECONDS = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    """The sessions to show, after reconciliation, and the panes matching no session."""

    sessions: tuple[SessionRow, ...]
    orphans: tuple[str, ...]


def refresh(ctx: CliContext, env: TmuxEnv, *, include_ended: bool = False) -> Snapshot:
    """Read the panes, then reconcile; a tmux failure stops everything before any write.

    Raises:
        TmuxError: tmux could not be read.
    """
    sessions = list_sessions(ctx.db, include_ended=True)  # before the panes: see apply_refresh
    panes = list_panes(env.tmux)
    return apply_refresh(
        ctx.db,
        panes,
        include_ended=include_ended,
        sessions=sessions,
        unsettled=_unsettled(env.tmux, panes),
    )


def dead_pane_settled(output: str, now: float) -> bool:
    """Tell from `"<pane_dead_signal> <pane_dead_time>"` whether a status-less dead pane is final.

    A known signal settles it at once; otherwise tmux may still report the exit status for
    a short while, after which it is taken as lost (tmux 3.4 does lose it).
    """
    signal, _, died = output.partition(" ")
    if signal.strip() not in ("", "0"):
        return True
    return not died.strip().isdigit() or now - int(died) >= _SETTLE_SECONDS


def _unsettled(tmux: Tmux, panes: Sequence[PaneInfo]) -> frozenset[PaneId]:
    """Return the dead panes without status that tmux has not finished reporting on."""
    unsettled: set[PaneId] = set()
    for pane in panes:
        if not pane.dead or pane.dead_status is not None or pane.meute_id is None:
            continue
        try:
            output = tmux.run("display-message", "-p", "-t", pane.id, _DEAD_FORMAT)
        except CommandFailed:  # the pane vanished since it was listed: look again next time
            unsettled.add(pane.id)
            continue
        if not dead_pane_settled(output, time.time()):
            unsettled.add(pane.id)
    return frozenset(unsettled)


def apply_refresh(
    db: Database,
    panes: Sequence[PaneInfo],
    *,
    include_ended: bool = False,
    sessions: Sequence[Session] | None = None,
    unsettled: frozenset[PaneId] = frozenset(),
) -> Snapshot:
    """Record the reconciled states and return the rows: live sessions and those with a pane.

    With `include_ended`, ended sessions without a pane are returned too. `sessions`, when
    given, must have been read before `panes`: a session created in between then keeps its
    state instead of being marked unreachable for lack of a pane. The dead panes in `unsettled`
    do not end their session yet.
    """
    first = first_by_id(panes, lambda pane: pane.meute_id)
    observations = [
        PaneObservation(
            meute_id=meute_id,
            dead=pane.dead,
            exit_code=pane.dead_status,
            settled=pane.id not in unsettled,
        )
        for meute_id, pane in first.items()
    ]
    if sessions is None:
        sessions = list_sessions(db, include_ended=True)
    result = reconcile(sessions, observations)
    for session_id, state in result.updates:
        set_session_state(db, session_id, state)
    if result.updates:
        sessions = list_sessions(db, include_ended=True)
    rows = (
        SessionRow(
            session=session,
            has_pane=session.id in first,
            displayed=session.id in first and first[session.id].session == MAIN_SESSION,
        )
        for session in sessions
    )
    shown = tuple(
        row for row in rows if include_ended or row.has_pane or is_live(row.session.state)
    )
    return Snapshot(sessions=shown, orphans=result.orphans)
