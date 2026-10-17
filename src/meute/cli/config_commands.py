"""`meute config path`, `get` and `set`."""

import os
from pathlib import Path
from typing import Annotated

import typer

from meute.cli.config_edit import config_set
from meute.core.config import config_get, ensure_config
from meute.core.paths import Paths

config_app = typer.Typer(no_args_is_help=True, help="Show and change the configuration.")


def _config_file() -> Path:
    return Paths.from_env(os.environ, home=Path.home()).config_file


@config_app.command("path")
def path_() -> None:
    """Print the configuration file's path."""
    typer.echo(_config_file())


@config_app.command("get")
def get(key: Annotated[str, typer.Argument(help="For example ui.board_width.")]) -> None:
    """Print the value of a key: the file's, else the default."""
    path = _config_file()
    ensure_config(path)
    typer.echo(config_get(path, key))


@config_app.command("set")
def set_(
    key: Annotated[str, typer.Argument(help="For example ui.board_width.")],
    value: Annotated[str, typer.Argument(help='A TOML value (72, ["a"]) or plain text.')],
) -> None:
    """Change a key, keeping the file's comments."""
    path = _config_file()
    ensure_config(path)
    config_set(path, key, value)
