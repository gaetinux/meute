"""Folder names and hook words must never be expanded as tmux formats (`#(shell)`, `#H`...)."""

from pathlib import Path

import pytest

from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec, render_config
from meute.tmux.panes import Spawn, list_panes, spawn_window
from meute.tmux.quote import format_literal
from support import wait_until
from tmux_support import TestServer

SLEEP = ("sh", "-c", "sleep 3600")
INJECTION = '#(touch "$MEUTE_MARKER")'


def test_format_literal_doubles_every_hash() -> None:
    assert format_literal("a#{b}##(c)") == "a##{b}####(c)"
    assert format_literal("plain") == "plain"
    assert format_literal("") == ""


def arm_marker(tmux: Tmux, tmp_path: Path) -> Path:
    """Point `$MEUTE_MARKER` of the tmux jobs to a file that must never be created."""
    marker = tmp_path / "pwned"
    tmux.run("set-environment", "-g", "MEUTE_MARKER", str(marker))
    return marker


def settle(tmux: Tmux, tmp_path: Path) -> None:
    """Wait for a later `#()` job to run, so that an earlier injected one had its chance."""
    sentinel = tmp_path / "sentinel"

    def sentinel_ran() -> bool:
        # A `-p` job dies with its short-lived client, so start it again until one has run.
        tmux.run("display-message", "-p", f"#(touch {sentinel})")
        return sentinel.exists()

    wait_until("the sentinel job", sentinel_ran)


@pytest.mark.parametrize("folder", [f"p{INJECTION}", "a#Hb"])
def test_spawn_cwd_is_taken_literally(tmux_server: TestServer, tmp_path: Path, folder: str) -> None:
    tmux = tmux_server.tmux
    marker = arm_marker(tmux, tmp_path)
    cwd = tmp_path / folder
    cwd.mkdir()
    pane = spawn_window(tmux, Spawn(session="bg", cwd=cwd, command=SLEEP))
    path = tmux.run("display-message", "-p", "-t", pane, "#{pane_current_path}")
    settle(tmux, tmp_path)
    assert path == str(cwd.resolve())
    assert not marker.exists()
    assert any(p.id == pane for p in list_panes(tmux))


def test_sync_hook_passes_words_literally(tmux_server: TestServer, tmp_path: Path) -> None:
    tmux = tmux_server.tmux
    marker = arm_marker(tmux, tmp_path)
    received = tmp_path / "argv"
    script = tmp_path / "record.sh"
    script.write_text(
        f"#!/bin/sh\nprintf '%s' \"$1\" > '{received}.tmp' && mv '{received}.tmp' '{received}'\n"
    )
    script.chmod(0o755)
    word = f'x{INJECTION}; it\'s \\ $HOME "ok"'
    spec = LayoutSpec(
        board_width=60,
        narrow_threshold=120,
        board_command=SLEEP,
        welcome_command=SLEEP,
        sync_command=(str(script), word),
        keys=Keys(focus_board="M-p", focus_main="M-o"),
    )
    conf = tmp_path / "tmux.conf"
    conf.write_text(render_config(spec))
    tmux.run("source-file", str(conf))
    tmux.run("set-hook", "-R", "client-attached")
    wait_until("the sync command", received.exists)
    settle(tmux, tmp_path)
    assert received.read_text() == word
    assert not marker.exists()
