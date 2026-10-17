"""Command-line interface."""

import importlib.metadata
import os
import sqlite3
import sys
from collections.abc import Sequence

import typer

from meute.cli import task_commands as task_commands
from meute.cli.context import current_time
from meute.cli.project_commands import project_app
from meute.cli.render import task_line
from meute.cli.task_app import task_app
from meute.core.errors import MeuteError, NotFound, VersionConflict

app = typer.Typer(name="meute", add_completion=False, pretty_exceptions_enable=False)
app.add_typer(task_app, name="task")
app.add_typer(project_app, name="project")

_FAILURE = 1
_CONFLICT = 3
_NOT_FOUND = 4


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


def _fail(message: str, code: int) -> int:
    print(f"meute: {message}", file=sys.stderr)
    return code


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
    except VersionConflict as conflict:
        _fail(str(conflict), _CONFLICT)
        print(task_line(conflict.current, current_time(os.environ)), file=sys.stderr)
        return _CONFLICT
    except NotFound as missing:
        return _fail(str(missing), _NOT_FOUND)
    except (MeuteError, OSError, sqlite3.Error) as error:
        return _fail(str(error), _FAILURE)
    return 0
