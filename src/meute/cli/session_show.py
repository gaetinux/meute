"""Showing a session in the main area of the `meute:main` window."""

from meute.cli.context import CliContext
from meute.cli.status_publish import publish_status
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.samples import latest_quota
from meute.core.db.sessions import get_session, list_sessions
from meute.core.errors import InvalidInput
from meute.core.quota_view import current_quota
from meute.core.session import SessionId
from meute.tmux.layout import ensure_layout, find_layout
from meute.tmux.names import MAIN_SESSION, MAIN_WINDOW, ROLE_WELCOME
from meute.tmux.panes import (
    kill_pane,
    list_panes,
    select_pane,
    swap_panes,
    switch_client_to,
)


def unreachable(title: str) -> InvalidInput:
    """Return the error of a session that has no pane any more."""
    return InvalidInput(f"session unreachable: {title}")


def show_session(ctx: CliContext, env: TmuxEnv, session_id: SessionId) -> None:
    """Bring the pane of a session into the main area and give it the focus.

    The previous occupant goes back to `meute-bg`, except the welcome pane, which is killed.
    A missing main area is repaired first.

    Raises:
        InvalidInput: meute is not open, or the session has no pane.
        TmuxError: tmux failed.
    """
    layout = find_layout(env.tmux)
    if layout is None:
        message = 'meute is not open: run "meute" first'
        raise InvalidInput(message)
    if layout.main is None:  # the main area was killed by hand: put the welcome pane back
        layout = ensure_layout(env.tmux, env.spec)
    session = get_session(ctx.db, session_id)
    panes = list_panes(env.tmux)
    pane = next((p for p in panes if p.meute_id == session_id), None)
    if pane is None:
        raise unreachable(session.title)
    if layout.zoomed:
        switch_client_to(env.tmux, pane.id)
        return
    if pane.session == MAIN_SESSION and pane.window == MAIN_WINDOW:
        select_pane(env.tmux, pane.id)
        return
    previous = next((p for p in panes if p.id == layout.main), None)
    if layout.main is not None:
        swap_panes(env.tmux, pane.id, layout.main)
        if previous is not None and previous.role == ROLE_WELCOME:
            kill_pane(env.tmux, previous.id)
    select_pane(env.tmux, pane.id)
    sample = latest_quota(ctx.db)
    quota = None if sample is None else current_quota(sample, now=ctx.db.now())
    _ = publish_status(
        env.tmux,
        session.title,
        list_sessions(ctx.db),
        None if quota is None else quota.five_hour_pct,
    )
