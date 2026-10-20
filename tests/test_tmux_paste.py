"""Pasting text into a pane through a private file and a tmux buffer, never a command argument."""

import stat
from pathlib import Path

import pytest

from meute.tmux.client import Tmux
from meute.tmux.errors import CommandFailed
from meute.tmux.panes import Spawn, paste_text, spawn_window
from meute.tmux.parse import PaneId
from support import wait_until
from tmux_support import TestServer

_TEXT = "first line\nsecond #{pane_id} line;"
_LOADED: list[tuple[int, str]] = []  # (mode, content) of each file handed to load-buffer


class _Watching(Tmux):
    """Notes the mode and content of the file given to `load-buffer`, then runs tmux."""

    def run(self, *args: str) -> str:
        if args[:1] == ("load-buffer",):
            path = Path(args[-1])
            _LOADED.append((stat.S_IMODE(path.stat().st_mode), path.read_text(encoding="utf-8")))
        return super().run(*args)


def _cat_pane(tmux: Tmux, tmp_path: Path) -> PaneId:
    return spawn_window(tmux, Spawn(session="paste", cwd=tmp_path, command=("cat", "-v")))


def test_text_arrives_as_is_and_no_file_is_left(tmux_server: TestServer, tmp_path: Path) -> None:
    private = tmp_path / "state"
    private.mkdir(mode=0o700)
    pane = _cat_pane(tmux_server.tmux, tmp_path)
    paste_text(tmux_server.tmux, pane, _TEXT, private_dir=private)

    def arrived() -> bool:
        # The terminal echo and cat's own output interleave: look for the lines, not their order.
        shown = tmux_server.tmux.run("capture-pane", "-p", "-t", pane)
        return shown.startswith("first line\n") and "second #{pane_id} line;" in shown

    wait_until("the pasted text", arrived)
    assert list(private.iterdir()) == []
    assert tmux_server.tmux.run("list-buffers") == ""  # the buffer was deleted after the paste


def test_the_file_is_private_and_holds_the_text(tmux_server: TestServer, tmp_path: Path) -> None:
    pane = _cat_pane(tmux_server.tmux, tmp_path)
    watching = _Watching(socket=tmux_server.tmux.socket, config_file=None)
    _LOADED.clear()
    paste_text(watching, pane, _TEXT, private_dir=tmp_path)
    assert _LOADED == [(0o600, _TEXT)]


def test_the_file_is_removed_when_tmux_fails(tmux_server: TestServer, tmp_path: Path) -> None:
    _ = _cat_pane(tmux_server.tmux, tmp_path)  # a server is running, the pane is not
    private = tmp_path / "state"
    private.mkdir(mode=0o700)
    with pytest.raises(CommandFailed):
        paste_text(tmux_server.tmux, PaneId("%999"), _TEXT, private_dir=private)
    assert list(private.iterdir()) == []
    assert tmux_server.tmux.run("list-buffers") == ""  # the text does not linger in tmux
