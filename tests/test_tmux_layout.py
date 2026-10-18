from meute.tmux.client import Tmux
from meute.tmux.conf import Keys, LayoutSpec
from meute.tmux.layout import ensure_layout, find_layout, is_narrow
from meute.tmux.panes import kill_pane, list_panes, send_keys
from meute.tmux.parse import PaneId, PaneInfo
from support import wait_until
from tmux_support import TestServer

SLEEP = ("sh", "-c", "sleep 3600")
SPEC = LayoutSpec(
    board_width=60,
    narrow_threshold=120,
    board_command=SLEEP,
    welcome_command=SLEEP,
    sync_command=("meute", "layout", "sync"),
    keys=Keys(focus_board="M-p", focus_main="M-o"),
)


def main_panes(tmux: Tmux) -> list[PaneInfo]:
    return [p for p in list_panes(tmux) if p.session == "meute" and p.window == "main"]


def roles(tmux: Tmux) -> list[str]:
    return sorted(p.role or "" for p in main_panes(tmux))


def pane_width(tmux: Tmux, pane: PaneId) -> int:
    return next(p.width for p in main_panes(tmux) if p.id == pane)


def test_is_narrow() -> None:
    assert is_narrow(119, 120)
    assert not is_narrow(120, 120)


def test_find_layout_without_session_is_none(tmux_server: TestServer) -> None:
    assert find_layout(tmux_server.tmux) is None


def test_fresh_server_gets_board_and_welcome(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    layout = ensure_layout(tmux, SPEC)
    assert roles(tmux) == ["board", "welcome"]
    assert layout.main is not None
    assert pane_width(tmux, layout.board) == 60
    assert not layout.zoomed
    assert layout.width == 200


def test_ensure_is_idempotent(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    first = ensure_layout(tmux, SPEC)
    second = ensure_layout(tmux, SPEC)
    assert first == second
    assert len(main_panes(tmux)) == 2


def test_killed_main_pane_is_replaced_by_welcome(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    first = ensure_layout(tmux, SPEC)
    assert first.main is not None
    kill_pane(tmux, first.main)
    layout = ensure_layout(tmux, SPEC)
    assert len(main_panes(tmux)) == 2
    assert layout.main is not None
    assert layout.main != first.main
    assert next(p.role for p in main_panes(tmux) if p.id == layout.main) == "welcome"
    assert pane_width(tmux, layout.board) == 60


def test_killed_board_is_recreated(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    first = ensure_layout(tmux, SPEC)
    kill_pane(tmux, first.board)
    layout = ensure_layout(tmux, SPEC)
    assert layout.board != first.board
    assert layout.main == first.main
    assert roles(tmux) == ["board", "welcome"]


def test_dead_board_is_replaced(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    tmux.run("set-option", "-g", "remain-on-exit", "on")
    dead_spec = LayoutSpec(
        board_width=60,
        narrow_threshold=120,
        board_command=("sh", "-c", "read line"),
        welcome_command=SLEEP,
        sync_command=SPEC.sync_command,
        keys=SPEC.keys,
    )
    first = ensure_layout(tmux, dead_spec)
    send_keys(tmux, first.board, "Enter")
    wait_until("the board to die", lambda: any(p.dead for p in main_panes(tmux)))
    layout = ensure_layout(tmux, SPEC)
    assert layout.board != first.board
    boards = [p for p in main_panes(tmux) if p.role == "board"]
    assert [p.id for p in boards] == [layout.board]
    assert not boards[0].dead


def test_missing_main_window_is_recreated(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    ensure_layout(tmux, SPEC)
    tmux.run("new-window", "-d", "-t", "=meute:", "-n", "other", "--", *SLEEP)
    tmux.run("kill-window", "-t", "=meute:main")
    assert find_layout(tmux) is None
    layout = ensure_layout(tmux, SPEC)
    assert roles(tmux) == ["board", "welcome"]
    assert layout.main is not None


def test_narrow_window_zooms_board_and_wide_unzooms(tmux_server: TestServer) -> None:
    tmux = tmux_server.tmux
    ensure_layout(tmux, SPEC)
    tmux.run("set-option", "-g", "window-size", "manual")
    tmux.run("resize-window", "-t", "=meute:main", "-x", "100")
    narrow = ensure_layout(tmux, SPEC)
    assert narrow.zoomed
    assert narrow.width == 100
    tmux.run("resize-window", "-t", "=meute:main", "-x", "200")
    wide = ensure_layout(tmux, SPEC)
    assert not wide.zoomed
    assert pane_width(tmux, wide.board) == 60
