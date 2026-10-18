"""Jumping to the next or previous session that needs attention."""

from collections.abc import Mapping

from meute.cli.board_data import load_board_data
from meute.cli.context import CliContext
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.attention import next_attention
from meute.core.board_sessions import board_sessions
from meute.core.session import Session, SessionId
from meute.core.sessions_view import SessionLine, ViewState
from meute.tmux.layout import main_window_panes

NOTHING_TO_JUMP_TO = "Nothing needs your attention."


def _displayed_id(env: TmuxEnv) -> SessionId | None:
    """Return the session shown in the main area of `meute:main`, if any."""
    shown = next(
        (pane.meute_id for pane in main_window_panes(env.tmux) if pane.meute_id),
        None,
    )
    return None if shown is None else SessionId(shown)


def jump_to_attention(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], *, backwards: bool
) -> Session | None:
    """Show the next (or previous) session needing attention, in the order of the board.

    The search starts from the displayed session and wraps around. When none needs attention,
    the client is told so and nothing changes. Returns the session shown, if any.

    Raises:
        InvalidInput: meute is not open.
        TmuxError: tmux failed.
    """
    # No `claude agents` here: assumed states stay the board's, which has its readings.
    data = load_board_data(ctx, env, environ, None, assume=False)
    board = board_sessions(data, ViewState())
    order = [
        board.infos[line.session_id].row.session
        for line in board.view.lines
        if isinstance(line, SessionLine) and line.session_id in board.infos
    ]
    target = next_attention(order, _displayed_id(env), backwards=backwards)
    if target is None:
        _ = env.tmux.run("display-message", NOTHING_TO_JUMP_TO)
        return None
    show_session(ctx, env, target.id)
    return target
