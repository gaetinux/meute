"""Jumping to the next or previous session that needs attention."""

import fcntl
import os
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_next import board_order
from meute.cli.session_show import show_session
from meute.cli.tmux_env import TmuxEnv
from meute.core.attention import next_attention
from meute.core.paths import make_private_dir
from meute.core.session import Session, SessionId
from meute.tmux.layout import main_window_panes

NOTHING_TO_JUMP_TO = "Nothing needs your attention."
_LOCK_NAME = "jump.lock"


@contextmanager
def _jump_lock(state_dir: Path) -> Generator[None]:
    """Hold an exclusive `flock` that serialises the jumps, so each sees the previous one."""
    make_private_dir(state_dir)
    fd = os.open(
        state_dir / _LOCK_NAME, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600
    )
    try:
        os.fchmod(fd, 0o600)  # the mode of `os.open` applies to a new file only
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)  # closing releases the lock


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
    # Two quick key presses start two jumps: the second must see where the first went.
    with _jump_lock(ctx.paths.state_dir):
        return _jump(ctx, env, environ, backwards=backwards)


def _jump(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], *, backwards: bool
) -> Session | None:
    order = board_order(ctx, env, environ)
    target = next_attention(order, _displayed_id(env), backwards=backwards)
    if target is None:
        _ = env.tmux.run("display-message", NOTHING_TO_JUMP_TO)
        return None
    show_session(ctx, env, target.id)
    return target
