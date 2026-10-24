"""The `meute state` commands: save, list, reopen and remove the saved states."""

import os
from typing import Annotated, NoReturn

import typer

from meute.cli.board_data import load_board_data
from meute.cli.confirm import confirmed
from meute.cli.context import local_now, open_context
from meute.cli.json_out import echo_json
from meute.cli.state_actions import save_live
from meute.cli.state_reopen import reopen_state
from meute.cli.tmux_env import open_tmux_env
from meute.core.db.saved_states import delete_state, get_state, list_states
from meute.core.errors import NotFound
from meute.core.instants import format_instant
from meute.core.saved_state import (
    reopen_text,
    session_count,
    stamp_name,
    state_line,
    state_name,
)
from meute.core.text import printable

state_app = typer.Typer(no_args_is_help=True, help="Saved states: sets of open sessions.")

_FAILURE = 1


def _unknown(error: NotFound) -> NoReturn:
    """Stop with exit code 1 (not the 4 of other missing things) and the error's text."""
    typer.echo(printable(f"meute: {error}"), err=True)
    raise typer.Exit(code=_FAILURE)


@state_app.command("save")
def save(
    name: Annotated[str | None, typer.Argument(help="The name (default: the local time).")] = None,
) -> None:
    """Save the live sessions, in the board order, under a name that is replaced if it exists."""
    with open_context(os.environ) as ctx:
        chosen = stamp_name(local_now(ctx)) if name is None else state_name(name)
        env = open_tmux_env(ctx, os.environ)
        # Like `board_order`: no `claude agents`, so assumed states stay the board's.
        data = load_board_data(ctx, env, os.environ, None, assume=False)
        sessions = save_live(ctx, data, chosen)
    typer.echo(f"Saved: {printable(chosen)} ({session_count(len(sessions))})")


@state_app.command("list")
def list_(*, json_: Annotated[bool, typer.Option("--json", help="Print JSON.")] = False) -> None:
    """List the saved states, `last` first, then from the newest to the oldest."""
    with open_context(os.environ) as ctx:
        states = list_states(ctx.db)
        now = ctx.db.now()
    if json_:
        echo_json(
            {
                "states": [
                    {
                        "name": state.name,
                        "created_at": format_instant(state.created_at),
                        "sessions": len(state.sessions),
                    }
                    for state in states
                ]
            }
        )
    else:
        for state in states:
            typer.echo(state_line(state, now))


@state_app.command("open")
def open_(name: Annotated[str, typer.Argument(help="The state's name.")]) -> None:
    """Reopen the sessions of a state; nothing running is stopped."""
    with open_context(os.environ) as ctx:
        try:
            state = get_state(ctx.db, name)
        except NotFound as error:
            _unknown(error)
        report = reopen_state(ctx, open_tmux_env(ctx, os.environ), os.environ, state)
    for line in reopen_text(report.reopened, report.skipped):
        typer.echo(line)


@state_app.command("rm")
def rm(
    name: Annotated[str, typer.Argument(help="The state's name.")],
    *,
    yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Remove a saved state; `last` too, which the board recreates."""
    with open_context(os.environ) as ctx:
        try:
            _ = get_state(ctx.db, name)
        except NotFound as error:
            _unknown(error)
        if not yes and not confirmed(f'Remove saved state "{printable(name)}"? [y/N]'):
            typer.echo("Cancelled.")
            return
        delete_state(ctx.db, name)
    typer.echo(f"Removed: {printable(name)}")
