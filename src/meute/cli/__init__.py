"""Command-line interface."""

import importlib.metadata
import os
import sqlite3
import sys
from collections.abc import Sequence

import typer

from meute.cli import task_commands as task_commands
from meute.cli import task_edit_commands as task_edit_commands
from meute.cli.board_backend import CliBoardBackend
from meute.cli.config_commands import config_app
from meute.cli.context import current_time, open_context
from meute.cli.layout_commands import layout_app, open_meute
from meute.cli.project_commands import project_app
from meute.cli.render import task_line
from meute.cli.repo_commands import repo_app
from meute.cli.repo_scan import scan_repos
from meute.cli.session_commands import session_app
from meute.cli.task_app import task_app
from meute.cli.tmux_env import open_tmux_env
from meute.cli.welcome import wait_forever, welcome_text
from meute.core.errors import MeuteError, VersionConflict
from meute.tmux.errors import TmuxError

app = typer.Typer(name="meute", add_completion=False, pretty_exceptions_enable=False)
app.add_typer(task_app, name="task")
app.add_typer(project_app, name="project")
app.add_typer(config_app, name="config")
app.add_typer(repo_app, name="repo")
app.add_typer(session_app, name="session")
app.add_typer(layout_app, name="layout", hidden=True)

_FAILURE = 1


def _print_version(value: bool) -> None:  # noqa: FBT001 — Typer callback signature
    if value:
        typer.echo(f"meute {importlib.metadata.version('meute')}")
        raise typer.Exit


@app.callback(invoke_without_command=True)
def _root(
    context: typer.Context,
    version: bool = typer.Option(  # noqa: FBT001 — Typer declares options as defaults
        False,  # noqa: FBT003 — Typer default
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Claude Code session manager: without a command, open meute in tmux."""
    _ = version  # handled by its eager callback
    if context.invoked_subcommand is None:
        open_meute(os.environ)


@app.command("board")
def board() -> None:
    """Run the dashboard (the right-hand pane of the layout)."""
    from meute.tui.board import BoardApp  # noqa: PLC0415 — keeps Textual out of every other command's start-up

    with open_context(os.environ) as ctx:
        env = open_tmux_env(ctx, os.environ)
        _ = scan_repos(ctx)
        BoardApp(CliBoardBackend(ctx, env, os.environ)).run()


@app.command("welcome", hidden=True)
def welcome() -> None:
    """Show the welcome text until the pane is killed."""
    with open_context(os.environ) as ctx:
        keys = ctx.config.keys
    typer.echo(welcome_text(keys))
    wait_forever()


def _fail(message: str) -> None:
    print(f"meute: {message}", file=sys.stderr)


def _exit_code(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return _FAILURE


def run(argv: Sequence[str]) -> int:
    """Run the CLI and return its exit code."""
    try:
        app(args=list(argv), prog_name="meute")
    except SystemExit as exit_:
        return _exit_code(exit_.code)
    except MeuteError as error:
        _fail(str(error))
        if isinstance(error, VersionConflict):
            print(task_line(error.current, current_time(os.environ)), file=sys.stderr)
        return error.exit_code
    except (OSError, sqlite3.Error, TmuxError) as error:
        _fail(str(error))
        return _FAILURE
    return 0
