"""Orphan panes: how tmux describes them, and how a line shows one."""

from pathlib import Path

import pytest

from meute.cli import session_refresh
from meute.cli.context import CliContext
from meute.cli.session_refresh import orphan_details, refresh
from meute.cli.tmux_env import TmuxEnv
from meute.core.actor import Actor, Author, Channel
from meute.core.config import Config
from meute.core.db.connection import Database
from meute.core.orphans import Orphan, orphan_line
from meute.core.paths import Paths
from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.names import ID_OPTION
from meute.tmux.panes import set_pane_option
from meute.tmux.parse import PaneId
from support import wait_until
from tmux_support import TestServer

HOME = Path("/home/me")


def _orphan(**fields: object) -> Orphan:
    base = {"meute_id": "x", "pane_id": "%1", "command": "claude", "cwd": "/srv", "dead": False}
    return Orphan(**(base | fields))  # pyright: ignore[reportArgumentType] — test helper


def _pane(server: TestServer, folder: Path, meute_id: str, command: str = "sleep 300") -> PaneId:
    tmux = server.tmux
    pane = PaneId(
        tmux.run(
            "new-window", "-d", "-P", "-F", "#{pane_id}", "-c", str(folder), "-t", "test:", command
        )
    )
    set_pane_option(tmux, pane, ID_OPTION, meute_id)
    wait_until(
        "command started",
        lambda: tmux.run("display-message", "-p", "-t", pane, "#{pane_current_command}") == "sleep",
    )
    return pane


def _env(server: TestServer, tmp_path: Path) -> TmuxEnv:
    spec = LayoutSpec(
        board_width=30,
        narrow_threshold=100,
        board_command=("b",),
        welcome_command=("w",),
        sync_command=("s",),
        keys=Keys(focus_board="a", focus_main="b"),
    )
    return TmuxEnv(tmux=server.tmux, spec=spec, config_file=tmp_path / "c")


def test_line_of_a_live_orphan() -> None:
    assert orphan_line(_orphan(cwd="/home/me/git/meute"), HOME) == "? claude  ~/git/meute  orphan"


def test_line_of_a_dead_orphan_says_dead() -> None:
    assert orphan_line(_orphan(dead=True), None) == "? claude  /srv  dead"


def test_line_keeps_an_outside_folder_whole() -> None:
    assert orphan_line(_orphan(cwd="/srv/x"), HOME) == "? claude  /srv/x  orphan"


def test_hostile_parts_become_one_printable_line() -> None:
    line = orphan_line(
        _orphan(meute_id="x\x1b[2Jy", command="claude\x1b[2J", cwd="/w\nrk;\x07\t\u202e"), HOME
    )
    assert "\n" not in line
    assert all(char.isprintable() for char in line)
    assert line.startswith("? claude�[2J  /w�rk;")


def test_details_read_the_command_and_the_folder_ending_in_a_semicolon(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    folder = tmp_path / "work;"
    folder.mkdir()
    pane = _pane(tmux_server, folder, "ghost")
    assert orphan_details(tmux_server.tmux, pane) == ("sleep", str(folder))


def test_details_split_on_the_first_tab_only(tmux_server: TestServer, tmp_path: Path) -> None:
    folder = tmp_path / "a\tb"
    folder.mkdir()
    pane = _pane(tmux_server, folder, "ghost")
    assert orphan_details(tmux_server.tmux, pane) == ("sleep", str(folder))


def test_details_of_a_vanished_pane_are_none(tmux_server: TestServer) -> None:
    assert orphan_details(tmux_server.tmux, PaneId("%999")) is None


def test_refresh_returns_the_complete_orphan(
    db: Database, tmux_server: TestServer, tmp_path: Path
) -> None:
    pane = _pane(tmux_server, tmp_path, "x;y")
    snapshot = refresh(_context(db, tmp_path), _env(tmux_server, tmp_path))
    assert snapshot.orphan_panes == (
        Orphan(meute_id="x;y", pane_id=pane, command="sleep", cwd=str(tmp_path), dead=False),
    )
    assert snapshot.orphans == ("x;y",)


def test_refresh_omits_a_pane_that_vanished_before_it_was_described(
    db: Database, tmux_server: TestServer, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _pane(tmux_server, tmp_path, "ghost")

    def vanished(_tmux: Tmux, _pane: PaneId) -> None:
        return None

    monkeypatch.setattr(session_refresh, "orphan_details", vanished)
    snapshot = refresh(_context(db, tmp_path), _env(tmux_server, tmp_path))
    assert (snapshot.orphan_panes, snapshot.orphans) == ((), ("ghost",))


def _context(db: Database, tmp_path: Path) -> CliContext:
    return CliContext(
        db=db,
        now=db.now(),
        actor=Actor(author=Author.USER, channel=Channel.CLI),
        config=Config(),
        paths=Paths.from_roots(config_home=tmp_path, data_home=tmp_path, state_home=tmp_path),
    )
