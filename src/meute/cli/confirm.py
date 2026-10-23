"""Asking the user to confirm on the terminal."""

import sys

import typer


def confirmed(prompt: str, *, err: bool = True) -> bool:
    """Write `prompt` (on stderr unless `err` is false); return whether `y` or `yes` was typed."""
    typer.echo(prompt, err=err, nl=False)
    return sys.stdin.readline().strip().lower() in {"y", "yes"}
