"""Command-line interface."""

import importlib.metadata
import os
import sqlite3
import sys
from collections.abc import Sequence

import typer

from meute.cli import task_commands as task_commands
from meute.cli import task_edit_commands as task_edit_commands
from meute.cli.config_commands import config_app
from meute.cli.context import current_time
from meute.cli.project_commands import project_app
from meute.cli.render import task_line
from meute.cli.repo_commands import repo_app
from meute.cli.session_commands import session_app
from meute.cli.task_app import task_app
from meute.core.errors import MeuteError, VersionConflict
from meute.tmux.errors import TmuxError

app = typer.Typer(name="meute", add_completion=False, pretty_exceptions_enable=False)
app.add_typer(task_app, name="task")
app.add_typer(project_app, name="project")
app.add_typer(config_app, name="config")
app.add_typer(repo_app, name="repo")
app.add_typer(session_app, name="session")

_FAILURE = 1


def _print_version(value: bool) -> None:  # noqa: FBT001 — Typer callback signature
    if value:
        typer.echo(f"meute {importlib.metadata.version('meute')}")
        raise typer.Exit


@app.callback()
def _root(
    version: bool = typer.Option(  # noqa: FBT001 — Typer declares options as defaults
        False,  # noqa: FBT003 — Typer default
        "--version",
        callback=_print_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Claude Code session manager."""


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
