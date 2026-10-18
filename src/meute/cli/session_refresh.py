"""Reading the sessions: tmux is observed, the database is reconciled, then the rows are built."""

import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from meute.cli.context import CliContext
from meute.cli.tmux_env import TmuxEnv
from meute.core.agents import AgentInfo, assumed_state, outside_agents
from meute.core.board_view import SessionRow
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.connection import Database
from meute.core.db.sessions import list_sessions, set_session_state
from meute.core.reconcile import PaneObservation, first_by_id, reconcile
from meute.core.session import AgentKind, Session
from meute.core.session_state import is_live
from meute.tmux.client import Tmux
from meute.tmux.errors import CommandFailed
from meute.tmux.names import MAIN_SESSION
from meute.tmux.panes import list_panes
from meute.tmux.parse import PaneId, PaneInfo

_DEAD_FORMAT = "#{pane_dead_signal} #{pane_dead_time}"
_SETTLE_SECONDS = 3


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentsReading:
    """What `claude agents --json` said, with the clock and threshold to judge silence by."""

    agents: Sequence[AgentInfo]
    now: datetime
    stuck_after: timedelta


@dataclass(frozen=True, slots=True, kw_only=True)
class Snapshot:
    """The sessions to show, after reconciliation, and the panes matching no session."""

    sessions: tuple[SessionRow, ...]
    orphans: tuple[str, ...]
    outside: tuple[AgentInfo, ...] = ()


def refresh(
    ctx: CliContext,
    env: TmuxEnv,
    *,
    include_ended: bool = False,
    agents: Sequence[AgentInfo] | None = None,
) -> Snapshot:
    """Read the panes, then reconcile; a tmux failure stops everything before any write.

    With `agents` (from `claude agents --json`), silent Claude sessions get their assumed state
    and the agents outside meute are returned. Without `agents` (not consulted, or failed) only
    the silence rule applies: a silent running session is `stuck?`.

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
        reading=AgentsReading(
            agents=() if agents is None else agents,
            now=ctx.db.now(),  # live: the context's own clock stops when the board starts
            stuck_after=timedelta(minutes=ctx.config.claude.stuck_after_minutes),
        ),
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


def apply_refresh(  # noqa: PLR0913 — one keyword per independent input of a reading
    db: Database,
    panes: Sequence[PaneInfo],
    *,
    include_ended: bool = False,
    sessions: Sequence[Session] | None = None,
    unsettled: frozenset[PaneId] = frozenset(),
    reading: AgentsReading | None = None,
) -> Snapshot:
    """Record the reconciled states and return the rows: live sessions and those with a pane.

    With `include_ended`, ended sessions without a pane are returned too. `sessions`, when
    given, must have been read before `panes`: a session created in between then keeps its
    state instead of being marked unreachable for lack of a pane. The dead panes in `unsettled`
    do not end their session yet. When `reading` is given, the assumed states are
    recorded after the reconciliation (see `assumed_state`) and the outside agents returned.
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
    outside: tuple[AgentInfo, ...] = ()
    if reading is not None:
        outside, changed = _apply_agents(db, sessions, reading)
        if changed:
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
    return Snapshot(sessions=shown, orphans=result.orphans, outside=outside)


def _apply_agents(
    db: Database,
    sessions: Sequence[Session],
    reading: AgentsReading,
) -> tuple[tuple[AgentInfo, ...], bool]:
    """Record the assumed states; return the agents outside meute and whether a state changed."""
    native = {
        session.id: details.native_id
        for session in sessions
        if session.agent is AgentKind.CLAUDE
        and (details := get_claude_details(db, session.id)).native_id
    }
    by_id = {agent.session_id: agent for agent in reading.agents}
    changed = False
    for session in sessions:
        native_id = native.get(session.id)
        agent = by_id.get(session.id) or (by_id.get(native_id) if native_id else None)
        state = assumed_state(session, agent, now=reading.now, stuck_after=reading.stuck_after)
        if state is not None:
            set_session_state(db, session.id, state)
            changed = True
    return outside_agents(reading.agents, sessions, native_ids=native.values()), changed
