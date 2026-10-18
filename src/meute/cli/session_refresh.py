"""Reading the sessions: tmux is observed, the database is reconciled, then the rows are built."""

from collections.abc import Sequence
from dataclasses import dataclass

from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_view import SessionRow
from meute.core.db.connection import Database
from meute.core.db.sessions import list_sessions, set_session_state
from meute.core.reconcile import PaneObservation, reconcile
from meute.core.session_state import is_live
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
from meute.tmux.parse import PaneInfo


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
    return apply_refresh(ctx.db, list_panes(env.tmux), include_ended=include_ended)


def apply_refresh(
    db: Database, panes: Sequence[PaneInfo], *, include_ended: bool = False
) -> Snapshot:
    """Record the reconciled states and return the rows: live sessions and those with a pane.

    With `include_ended`, ended sessions without a pane are returned too.
    """
    # The first pane carrying an identifier counts, as in `reconcile`.
    first: dict[str, PaneInfo] = {}
    for pane in panes:
        if pane.meute_id is not None:
            first.setdefault(pane.meute_id, pane)
    observations = [
        PaneObservation(meute_id=meute_id, dead=pane.dead, exit_code=pane.dead_status)
        for meute_id, pane in first.items()
    ]
    result = reconcile(list_sessions(db, include_ended=True), observations)
    for session_id, state in result.updates:
        set_session_state(db, session_id, state)
    rows = tuple(
        SessionRow(
            session=session,
            has_pane=session.id in first,
            displayed=session.id in first and first[session.id].session == MAIN_SESSION,
        )
        for session in list_sessions(db, include_ended=True)
    )
    shown = tuple(
        row for row in rows if include_ended or row.has_pane or is_live(row.session.state)
    )
    return Snapshot(
        sessions=shown,
        orphans=result.orphans,
    )
