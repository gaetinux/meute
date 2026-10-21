"""Restarting a dead pane in place with `respawn-pane -k`."""

import os
from dataclasses import replace
from pathlib import Path

from meute.tmux.panes import Spawn, list_panes, respawn_window, spawn_window
from meute.tmux.parse import PaneId, PaneInfo
from support import wait_until
from tmux_support import TestServer


def _find(server: TestServer, pane: PaneId) -> PaneInfo | None:
    return next((p for p in list_panes(server.tmux) if p.id == pane), None)


def test_respawn_restarts_a_dead_pane_in_place(tmux_server: TestServer, tmp_path: Path) -> None:
    tmux = tmux_server.tmux
    folder = tmp_path / "repo;"
    folder.mkdir()
    out = tmp_path / "out.txt"
    dying = Spawn(
        session="bg",
        cwd=folder,
        command=("sh", "-c", "sleep 0.3"),
        pane_options=(("@meute_id", "me"), ("remain-on-exit", "on")),
    )
    pane = spawn_window(tmux, dying)
    wait_until("the pane to die", lambda: (p := _find(tmux_server, pane)) is not None and p.dead)
    again = replace(
        dying,
        command=("sh", "-c", 'pwd > "$OUT"; echo "$MEUTE_SESSION" >> "$OUT"; sleep 3600'),
        env=(("OUT", str(out)), ("MEUTE_SESSION", "me")),
    )
    assert respawn_window(tmux, pane, again) == pane
    wait_until("the output file", lambda: out.exists() and out.read_text().count("\n") == 2)
    assert out.read_text().splitlines() == [os.path.realpath(folder), "me"]
    info = _find(tmux_server, pane)
    assert info is not None
    assert (info.dead, info.meute_id) == (False, "me")
    assert tmux.run("show-options", "-p", "-t", pane, "remain-on-exit").strip() == (
        "remain-on-exit on"
    )
