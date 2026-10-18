"""The tmux environment of a command: socket, generated configuration and layout spec."""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from meute.cli.context import CliContext
from meute.core.config import write_atomic
from meute.tmux.client import Tmux, check_version
from meute.tmux.conf import Keys, LayoutSpec, render_config

DEFAULT_SOCKET = "meute"


def meute_command() -> tuple[str, ...]:
    """The command that starts meute again, whatever the way it was installed."""
    return (sys.executable, "-m", "meute")


@dataclass(frozen=True, slots=True, kw_only=True)
class TmuxEnv:
    """A tmux client, the layout it is built for and the generated configuration file."""

    tmux: Tmux
    spec: LayoutSpec
    config_file: Path


def open_tmux_env(ctx: CliContext, environ: Mapping[str, str]) -> TmuxEnv:
    """Check tmux, write the generated configuration and return the client.

    Raises:
        NotInstalled: the tmux binary is missing.
        TooOld: the installed tmux is older than 3.2.
    """
    check_version()
    command = meute_command()
    spec = LayoutSpec(
        board_width=ctx.config.ui.board_width,
        narrow_threshold=ctx.config.ui.narrow_threshold,
        board_command=(*command, "board"),
        welcome_command=(*command, "welcome"),
        sync_command=(*command, "layout", "sync"),
        keys=Keys(focus_board=ctx.config.keys.focus_board, focus_main=ctx.config.keys.focus_main),
    )
    config_file = ctx.paths.state_dir / "tmux.conf"
    write_atomic(config_file, render_config(spec))
    socket = environ.get("MEUTE_TMUX_SOCKET") or DEFAULT_SOCKET
    return TmuxEnv(
        tmux=Tmux(socket=socket, config_file=config_file), spec=spec, config_file=config_file
    )
