"""Showing a session in the main area of the `meute:main` window."""

from meute.cli.context import CliContext
from meute.cli.status_publish import publish_status
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.samples import latest_quota
from meute.core.db.sessions import get_session, list_sessions
from meute.core.errors import InvalidInput
from meute.core.quota_view import current_quota
from meute.core.session import SessionId
from meute.tmux.layout import Layout, ensure_layout, find_layout
from meute.tmux.names import MAIN_SESSION, MAIN_WINDOW, ROLE_WELCOME
from meute.tmux.panes import (
    kill_pane,
    list_panes,
    select_pane,
    swap_panes,
    switch_client_to,
)
from meute.tmux.parse import PaneInfo


def unreachable(title: str) -> InvalidInput:
    """Return the error of a session that has no pane any more."""
    return InvalidInput(f"session unreachable: {title}")


def _open_layout(env: TmuxEnv) -> Layout:
    """Return the layout with a main area, repairing a missing one."""
    layout = find_layout(env.tmux)
    if layout is None:
        message = 'meute is not open: run "meute" first'
        raise InvalidInput(message)
    if layout.main is None:  # the main area was killed by hand: put the welcome pane back
        layout = ensure_layout(env.tmux, env.spec)
    return layout


def _bring(env: TmuxEnv, layout: Layout, pane: PaneInfo) -> bool:
    """Put `pane` in the main area and focus it; `False` when it was already there or zoomed."""
    if layout.zoomed:
        switch_client_to(env.tmux, pane.id)
        return False
    if pane.session == MAIN_SESSION and pane.window == MAIN_WINDOW:
        select_pane(env.tmux, pane.id)
        return False
    previous = next((p for p in list_panes(env.tmux) if p.id == layout.main), None)
    if layout.main is not None:
        swap_panes(env.tmux, pane.id, layout.main)
        if previous is not None and previous.role == ROLE_WELCOME:
            kill_pane(env.tmux, previous.id)
    select_pane(env.tmux, pane.id)
    return True


def show_pane(env: TmuxEnv, pane: PaneInfo) -> None:
    """Bring a live pane into the main area and give it the focus.

    Raises:
        InvalidInput: meute is not open, or the pane is dead.
        TmuxError: tmux failed.
    """
    layout = _open_layout(env)
    if pane.dead:
        message = "dead pane: nothing to show"
        raise InvalidInput(message)
    _ = _bring(env, layout, pane)


def show_session(ctx: CliContext, env: TmuxEnv, session_id: SessionId) -> None:
    """Bring the pane of a session into the main area and give it the focus.

    The previous occupant goes back to `meute-bg`, except the welcome pane, which is killed.
    A missing main area is repaired first.

    Raises:
        InvalidInput: meute is not open, or the session has no pane.
        TmuxError: tmux failed.
    """
    layout = _open_layout(env)
    session = get_session(ctx.db, session_id)
    pane = next((p for p in list_panes(env.tmux) if p.meute_id == session_id), None)
    if pane is None:
        raise unreachable(session.title)
    if not _bring(env, layout, pane):
        return
    sample = latest_quota(ctx.db)
    quota = None if sample is None else current_quota(sample, now=ctx.db.now())
    _ = publish_status(
        env.tmux,
        session.title,
        list_sessions(ctx.db),
        None if quota is None else quota.five_hour_pct,
    )
