"""What the board does with an orphan pane: show it, adopt it as a session, close it."""

import sqlite3
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_show import show_pane
from meute.cli.session_stop import STOP_GRACE_SECONDS, interrupt_and_kill
from meute.cli.tmux_env import TmuxEnv
from meute.core.db.repos import list_repos
from meute.core.db.sessions import create_session, get_session
from meute.core.errors import InvalidInput, NotFound
from meute.core.orphans import Orphan, adoption
from meute.core.session import AgentKind, Session, SessionId
from meute.git.discover import main_repo_of
from meute.tmux.layout import ensure_layout, find_layout
from meute.tmux.panes import list_panes, pane_by_id


def show_orphan(env: TmuxEnv, pane_id: str) -> None:
    """Bring the orphan pane `pane_id` into the main area.

    Only a pane tmux lists reaches the commands: `pane_id` selects among them.

    Raises:
        InvalidInput: meute is not open, the pane is gone or dead.
        TmuxError: tmux failed.
    """
    pane = pane_by_id(list_panes(env.tmux), pane_id)
    if pane is None:
        message = "pane is gone"
        raise InvalidInput(message)
    show_pane(env, pane)


def _recorded(ctx: CliContext, session_id: SessionId) -> bool:
    try:
        _ = get_session(ctx.db, session_id)
    except NotFound:
        return False
    return True


def adopt_orphan(ctx: CliContext, orphan: Orphan) -> Session | None:
    """Record the orphan pane as a session; `None` when its identifier is already recorded.

    Raises:
        InvalidInput: the orphan cannot be adopted (not a meute id, dead pane).
    """
    cwd = Path(orphan.cwd)
    main = main_repo_of(cwd) if cwd.is_absolute() else None
    new = adoption(orphan, list_repos(ctx.db), main)
    if isinstance(new, str):
        raise InvalidInput(new)
    if _recorded(ctx, new.id):
        return None
    try:
        return create_session(ctx.db, new)
    except sqlite3.IntegrityError:
        if _recorded(ctx, new.id):  # another adoption won the race
            return None
        raise


def close_orphan(env: TmuxEnv, meute_id: str, agent: AgentKind) -> None:
    """Interrupt and kill the orphan pane tagged `meute_id`; nothing is written to the database.

    `meute_id` may be anything tmux holds: it only selects among the listed panes. A pane
    already gone does nothing. The layout is repaired afterwards, like after a stop.

    Raises:
        TmuxError: tmux failed.
    """
    _ = interrupt_and_kill(env, meute_id, STOP_GRACE_SECONDS, twice=agent is AgentKind.CLAUDE)
    if find_layout(env.tmux) is not None:
        _ = ensure_layout(env.tmux, env.spec)
