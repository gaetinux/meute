"""`meute session new`."""

import os
from pathlib import Path
from typing import Annotated, assert_never

import typer

from meute.cli.context import open_context
from meute.cli.session_launch import BashLaunch, launch_bash
from meute.cli.tmux_env import open_tmux_env
from meute.core.errors import InvalidInput
from meute.core.paths import display_path
from meute.core.session import AgentKind, short_id

session_app = typer.Typer(no_args_is_help=True, help="Sessions running in tmux.")


@session_app.command("new")
def new(
    cwd: Annotated[
        Path | None, typer.Option("--cwd", help="Folder to start in (default: here).")
    ] = None,
    title: Annotated[str | None, typer.Option("--title", help="Session title.")] = None,
    kind: Annotated[AgentKind, typer.Option("--kind", help="What to run.")] = AgentKind.BASH,
) -> None:
    """Start a session in the background."""
    match kind:
        case AgentKind.CLAUDE:
            message = "only bash sessions are available for now"
            raise InvalidInput(message)
        case AgentKind.BASH:
            pass
        case _:
            assert_never(kind)
    with open_context(os.environ) as ctx:
        env = open_tmux_env(ctx, os.environ)
        request = BashLaunch(cwd=cwd or Path.cwd(), title=title)
        session = launch_bash(ctx, env, request, os.environ)
    typer.echo(
        f"Launched: {short_id(session.id)} {session.title} "
        f"({display_path(session.cwd, Path.home())})"
    )
