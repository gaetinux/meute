"""Panes: listing, spawning windows, options, swapping and killing."""

from dataclasses import dataclass
from pathlib import Path

from meute.tmux.client import Tmux, is_no_server
from meute.tmux.errors import CommandFailed
from meute.tmux.parse import PANE_FORMAT, PaneId, PaneInfo, parse_pane_line


@dataclass(frozen=True, slots=True, kw_only=True)
class Spawn:
    """A command to start in a new window of `session`, created if missing."""

    session: str
    cwd: Path
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    pane_options: tuple[tuple[str, str], ...] = ()


def list_panes(tmux: Tmux) -> list[PaneInfo]:
    """List every pane of the server; no server means no panes.

    Raises:
        CommandFailed: tmux failed for a reason other than a missing server.
        UnreadableOutput: a pane line could not be parsed.
    """
    try:
        output = tmux.run("list-panes", "-a", "-F", PANE_FORMAT)
    except CommandFailed as error:
        if is_no_server(error):
            return []
        raise
    return [parse_pane_line(line) for line in output.splitlines()]


_CD_THEN_EXEC = 'cd -- "$1" || exit; shift; exec "$@"'


def _in_folder(spawn: Spawn) -> tuple[str, ...]:
    """Wrap the command so the folder travels as argv data, never parsed by tmux."""
    return ("/bin/sh", "-c", _CD_THEN_EXEC, "meute", str(spawn.cwd), *spawn.command)


def spawn_window(tmux: Tmux, spawn: Spawn) -> PaneId:
    """Start `spawn.command` in a new window, then set the pane options in order."""
    if tmux.has_session(spawn.session):
        create = ["new-window", "-d", "-t", f"={spawn.session}:"]
    else:
        create = ["new-session", "-d", "-s", spawn.session]
    env_args = [arg for key, value in spawn.env for arg in ("-e", f"{key}={value}")]
    pane = PaneId(
        tmux.run(
            *create,
            "-P",
            "-F",
            "#{pane_id}",
            *env_args,
            "--",
            *_in_folder(spawn),
        )
    )
    for name, value in spawn.pane_options:
        set_pane_option(tmux, pane, name, value)
    return pane


def set_pane_option(tmux: Tmux, pane: PaneId, name: str, value: str) -> None:
    """Set a pane option."""
    tmux.run("set-option", "-p", "-t", pane, name, value)


def set_global_option(tmux: Tmux, name: str, value: str) -> None:
    """Set a global (server) option."""
    tmux.run("set-option", "-g", name, value)


def swap_panes(tmux: Tmux, src: PaneId, dst: PaneId) -> None:
    """Swap two panes without changing the active one."""
    tmux.run("swap-pane", "-d", "-s", src, "-t", dst)


def select_pane(tmux: Tmux, pane: PaneId) -> None:
    """Give the focus to a pane."""
    tmux.run("select-pane", "-t", pane)


def send_keys(tmux: Tmux, pane: PaneId, *keys: str) -> None:
    """Send keys to a pane."""
    tmux.run("send-keys", "-t", pane, "--", *keys)


def kill_pane(tmux: Tmux, pane: PaneId) -> None:
    """Kill a pane."""
    tmux.run("kill-pane", "-t", pane)


def switch_client_to(tmux: Tmux, pane: PaneId) -> None:
    """Switch the attached client to the session holding a pane."""
    tmux.run("switch-client", "-t", pane)
