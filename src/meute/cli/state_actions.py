"""The board's `S` and `O`: save its sessions as a state, reopen a saved state."""

from collections.abc import Mapping
from dataclasses import replace
from typing import NoReturn

from meute.cli.context import CliContext, local_now, open_database
from meute.cli.state_reopen import reopen_state
from meute.cli.tmux_env import TmuxEnv
from meute.core.board_sessions import board_session_order
from meute.core.board_view import BoardData
from meute.core.db.saved_states import get_state, save_state
from meute.core.errors import ActionNotice
from meute.core.saved_state import reopen_text, saved_text, stamp_name
from meute.core.state_capture import capture
from meute.core.text import printable


def save_board_state(ctx: CliContext, data: BoardData) -> NoReturn:
    """Save the live sessions of `data`, in the board order, under the local time.

    Raises:
        ActionNotice: always, once saved: `state saved: <name>`.
    """
    name = stamp_name(local_now(ctx))
    _ = save_state(ctx.db, name, capture(data, board_session_order(data)))
    raise ActionNotice(saved_text(name))


def reopen_board_state(
    ctx: CliContext, env: TmuxEnv, environ: Mapping[str, str], name: str
) -> NoReturn:
    """Reopen the state `name` on a connection of its own: the board runs this in a worker.

    Raises:
        NotFound: no state has that name.
        ActionNotice: once reopened: `reopened <n> · skipped <m>`.
    """
    with open_database(ctx.paths, ctx.db.clock) as db:
        ctx = replace(ctx, db=db)
        report = reopen_state(ctx, env, environ, get_state(db, name))
    raise ActionNotice(printable(reopen_text(report.reopened, report.skipped)[0]))
