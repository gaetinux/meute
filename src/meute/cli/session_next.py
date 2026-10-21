"""Showing the next live session once the displayed pane is stopped or closed."""

from collections.abc import Mapping, Sequence

from meute.cli.board_data import load_board_data
from meute.cli.context import CliContext
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.attention import next_live
from meute.core.board_sessions import board_sessions
from meute.core.errors import InvalidInput
from meute.core.session import Session
from meute.core.sessions_view import SessionLine, ViewState
from meute.tmux.errors import TmuxError
from meute.tmux.layout import displayed_meute_id


def board_order(ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str]) -> list[Session]:
    """Return the sessions in the order of the board's Sessions view.

    Raises:
        TmuxError: tmux failed.
    """
    # No `claude agents` here: assumed states stay the board's, which has its readings.
    data = load_board_data(ctx, env, environ, None, assume=False)
    board = board_sessions(data, ViewState())
    return [
        board.infos[line.session_id].row.session
        for line in board.view.lines
        if isinstance(line, SessionLine) and line.session_id in board.infos
    ]


def order_if_shown(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], meute_id: str
) -> list[Session]:
    """Return the board order when the pane tagged `meute_id` is the one shown, else nothing.

    Read before the pane goes, so that the next session is the one after it on the board. A
    tmux failure here gives nothing: the stop still happens and the welcome pane comes back.
    """
    try:
        if displayed_meute_id(env.tmux) != meute_id:
            return []
        return board_order(ctx, env, environ)
    except TmuxError:
        return []


def show_next(
    ctx: CliContext, env: TmuxEnv, order: Sequence[Session], meute_id: str
) -> Session | None:
    """Show the live session after `meute_id` in `order`, the board order read before it went.

    The welcome pane stays when no other session is live, or when the next one has lost its
    pane in the meantime. Returns the session shown, if any.

    Raises:
        TmuxError: tmux failed.
    """
    target = next_live(order, meute_id)
    if target is None:
        return None
    try:
        show_session(ctx, env, target.id)
    except InvalidInput:  # its pane went away too: the welcome pane is a fine place to land
        return None
    return target
