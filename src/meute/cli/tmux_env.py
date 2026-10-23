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
    """The command that starts meute again, whatever the way it was installed.

    `-P` keeps the current folder off `sys.path`: Claude runs the hooks and `meute mcp` in the
    session's folder, whose packages must not shadow meute's imports.
    """
    return (sys.executable, "-P", "-m", "meute")


def _write_if_changed(path: Path, text: str) -> None:
    try:
        if path.read_text(encoding="utf-8") == text:
            return
    except (OSError, UnicodeDecodeError):
        pass
    write_atomic(path, text)


@dataclass(frozen=True, slots=True, kw_only=True)
class TmuxEnv:
    """A tmux client, the layout it is built for and the generated configuration file."""

    tmux: Tmux
    spec: LayoutSpec
    config_file: Path


def meute_tmux(ctx: CliContext, environ: Mapping[str, str]) -> Tmux:
    """Return the client of meute's tmux server, without checking tmux or writing anything."""
    socket = environ.get("MEUTE_TMUX_SOCKET") or DEFAULT_SOCKET
    return Tmux(socket=socket, config_file=_config_file(ctx))


def _config_file(ctx: CliContext) -> Path:
    return ctx.paths.state_dir / "tmux.conf"


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
        attention_command=command,
        keys=Keys(
            focus_board=ctx.config.keys.focus_board,
            focus_main=ctx.config.keys.focus_main,
            next_attention=ctx.config.keys.next_attention,
            previous_attention=ctx.config.keys.previous_attention,
            detach=ctx.config.keys.detach,
            quick_task=ctx.config.keys.quick_task,
        ),
    )
    config_file = _config_file(ctx)
    _write_if_changed(config_file, render_config(spec))
    return TmuxEnv(tmux=meute_tmux(ctx, environ), spec=spec, config_file=config_file)
