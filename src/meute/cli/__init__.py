"""Command-line interface."""

import importlib.metadata
from collections.abc import Sequence

import typer

app = typer.Typer(name="meute", add_completion=False)


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


def run(argv: Sequence[str]) -> int:
    """Run the CLI and return its exit code."""
    try:
        app(args=list(argv), prog_name="meute")
    except SystemExit as exit_:
        return exit_.code if isinstance(exit_.code, int) else 1
    return 0
