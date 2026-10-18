import os
from pathlib import Path
from uuid import uuid4

import pytest

from meute.tmux.client import Tmux, is_no_server
from meute.tmux.errors import CommandFailed, NotInstalled
from meute.tmux.panes import (
    Spawn,
    kill_pane,
    list_panes,
    set_pane_option,
    spawn_window,
    swap_panes,
)
from meute.tmux.parse import PaneId, PaneInfo
from support import wait_until
from tmux_support import TestServer

SLEEP = ("sh", "-c", "sleep 3600")


def spawn(session: str, *, meute_id: str, cwd: Path = Path("/")) -> Spawn:
    return Spawn(session=session, cwd=cwd, command=SLEEP, pane_options=(("@meute_id", meute_id),))


def find(tmux: Tmux, pane: PaneId) -> PaneInfo | None:
    return next((p for p in list_panes(tmux) if p.id == pane), None)


def test_list_panes_on_never_started_socket_is_empty() -> None:
    assert list_panes(Tmux(socket="meute-test-never-started-panes")) == []


def test_list_panes_other_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    with pytest.raises(NotInstalled):
        list_panes(Tmux(socket=f"meute-test-never-started-{uuid4().hex}"))
    assert not is_no_server(CommandFailed(("x",), "unknown command: x"))


def test_spawn_creates_bg_session_then_windows(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    first = spawn_window(tmux, spawn("bg", meute_id="one"))
    second = spawn_window(tmux, spawn("bg", meute_id="two"))
    panes = {p.id: p for p in list_panes(tmux) if p.session == "bg"}
    assert set(panes) == {first, second}
    assert panes[first].meute_id == "one"
    assert panes[second].meute_id == "two"


def test_spawn_passes_cwd_and_env(tmux_server: TestServer, tmp_path: Path) -> None:
    cwd = tmp_path / "a dir"
    cwd.mkdir()
    out = tmp_path / "out.txt"
    spawn_window(
        tmux_server.tmux,
        Spawn(
            session="bg",
            cwd=cwd,
            command=(
                "sh",
                "-c",
                'pwd > "$OUT"; echo "$MEUTE_SESSION" >> "$OUT"; sleep 3600',
            ),
            env=(("OUT", str(out)), ("MEUTE_SESSION", "abc")),
        ),
    )
    wait_until("the output file", lambda: out.exists() and out.read_text().count("\n") == 2)
    assert out.read_text().splitlines() == [os.path.realpath(cwd), "abc"]


def test_remain_on_exit_keeps_dead_pane_with_status(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    spawn_window(tmux, spawn("bg", meute_id="keep"))
    pane = spawn_window(
        tmux,
        Spawn(
            session="bg",
            cwd=Path("/"),
            command=("sh", "-c", "sleep 0.3; exit 3"),
            pane_options=(("remain-on-exit", "on"),),
        ),
    )

    def dead() -> bool:
        info = find(tmux, pane)
        return info is not None and info.dead and info.dead_status is not None

    wait_until("the pane to die with its status", dead)
    info = find(tmux, pane)
    assert info is not None
    assert info.dead_status == 3


def test_meute_id_follows_the_pane_through_swap(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    a = spawn_window(tmux, spawn("one", meute_id="id-a"))
    b = spawn_window(tmux, spawn("two", meute_id="id-b"))
    swap_panes(tmux, a, b)
    after_a, after_b = find(tmux, a), find(tmux, b)
    assert after_a is not None
    assert after_b is not None
    assert (after_a.meute_id, after_a.session) == ("id-a", "two")
    assert (after_b.meute_id, after_b.session) == ("id-b", "one")


def test_kill_pane_removes_it(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    spawn_window(tmux, spawn("bg", meute_id="stay"))
    pane = spawn_window(tmux, spawn("bg", meute_id="go"))
    kill_pane(tmux, pane)
    assert find(tmux, pane) is None


def test_set_pane_option_is_readable(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    pane = spawn_window(tmux, spawn("bg", meute_id="x"))
    set_pane_option(tmux, pane, "@meute_role", "welcome")
    info = find(tmux, pane)
    assert info is not None
    assert info.role == "welcome"
