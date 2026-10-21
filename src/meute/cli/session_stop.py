"""Stopping a session: Ctrl-C (twice for Claude), then a kill after a grace period."""

import time
from collections.abc import Mapping

from meute.cli.context import CliContext
from meute.cli.session_next import order_if_shown, show_next
from meute.cli.session_refresh import refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.sessions import get_session, set_session_state
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import Exited, Unreachable, is_live
from meute.tmux.errors import CommandFailed
from meute.tmux.layout import ensure_layout, find_layout
from meute.tmux.panes import kill_pane, pane_of_session, send_keys
from meute.tmux.parse import PaneInfo

STOP_GRACE_SECONDS = 5.0
_POLL_SECONDS = 0.1
CLAUDE_SECOND_INTERRUPT_SECONDS = 0.3  # Claude quits on a second Ctrl-C shortly after the first


def _interrupt(env: TmuxEnv, meute_id: str, grace: float, *, twice: bool) -> PaneInfo | None:
    """Send Ctrl-C (twice for Claude) and wait until the pane is dead or gone, `grace` at most."""
    pane = pane_of_session(env.tmux, meute_id)
    if pane is None or pane.dead:
        return pane
    send_keys(env.tmux, pane.id, "C-c")
    if twice:
        time.sleep(CLAUDE_SECOND_INTERRUPT_SECONDS)
        pane = pane_of_session(env.tmux, meute_id)
        if pane is None or pane.dead:
            return pane
        send_keys(env.tmux, pane.id, "C-c")
    deadline = time.monotonic() + grace
    while True:
        pane = pane_of_session(env.tmux, meute_id)
        if pane is None or pane.dead or time.monotonic() >= deadline:
            return pane
        time.sleep(_POLL_SECONDS)


def _kill(env: TmuxEnv, pane: PaneInfo, meute_id: str) -> None:
    try:
        kill_pane(env.tmux, pane.id)
    except CommandFailed:
        # The pane may have died by itself in the meantime: only a pane still there is an error.
        if pane_of_session(env.tmux, meute_id) is not None:
            raise


def interrupt_and_kill(
    env: TmuxEnv, meute_id: str, grace: float, *, twice: bool
) -> PaneInfo | None:
    """Interrupt the pane tagged `meute_id`, then kill it; return it as it was before the kill.

    `meute_id` only selects among the listed panes: it never reaches tmux. A pane already gone
    does nothing and gives None.

    Raises:
        TmuxError: tmux failed.
    """
    pane = _interrupt(env, meute_id, grace, twice=twice)
    if pane is not None:
        _kill(env, pane, meute_id)
    return pane


def stop_session(
    ctx: CliContext,
    env: TmuxEnv,
    session_id: SessionId,
    *,
    grace: float = STOP_GRACE_SECONDS,
    environ: Mapping[str, str] | None = None,
) -> Session:
    """Interrupt the session (twice for Claude), kill it if it resists, and record it as exited.

    A session that already ended keeps its state. The layout is repaired afterwards, so that
    stopping the displayed session brings the welcome pane back; with `environ`, the next live
    session of the board is shown there instead, when there is one.

    Raises:
        NotFound: no such session.
        TmuxError: tmux failed.
    """
    refresh(ctx, env, assume=False)  # assumed states need `claude agents`: left to the board
    claude = get_session(ctx.db, session_id).agent is AgentKind.CLAUDE
    order = [] if environ is None else order_if_shown(ctx, env, environ, session_id)
    pane = interrupt_and_kill(env, session_id, grace, twice=claude)
    code = None if pane is None or not pane.dead else pane.dead_status
    session = get_session(ctx.db, session_id)
    # A reread by the board (another thread) between the kill and here sees the pane gone.
    killed = pane is not None and isinstance(session.state, Unreachable)
    if is_live(session.state) or killed:
        session = set_session_state(ctx.db, session_id, Exited(code=code))
    if find_layout(env.tmux) is not None:
        ensure_layout(env.tmux, env.spec)
        _ = show_next(ctx, env, order, session_id)
    return session
