"""The `meute:main` window: dashboard on the right, main area on the left."""

from dataclasses import dataclass

from meute.tmux.client import Tmux
from meute.tmux.conf import LayoutSpec
from meute.tmux.errors import UnreadableOutput
from meute.tmux.names import (
    MAIN_SESSION,
    MAIN_TARGET,
    MAIN_WINDOW,
    ROLE_BOARD,
    ROLE_OPTION,
    ROLE_WELCOME,
)
from meute.tmux.panes import kill_pane, list_panes, select_pane, set_pane_option
from meute.tmux.parse import PaneId, PaneInfo

_NO_BOARD = "no dashboard in meute:main"


@dataclass(frozen=True, slots=True, kw_only=True)
class Layout:
    """Current state of the `meute:main` window."""

    board: PaneId
    main: PaneId | None
    width: int
    zoomed: bool


def is_narrow(width: int, threshold: int) -> bool:
    """Whether a window of this width is too narrow for side-by-side panes."""
    return width < threshold


def main_window_panes(tmux: Tmux) -> list[PaneInfo]:
    """Return the panes of the main window of `meute:main`."""
    return [p for p in list_panes(tmux) if p.session == MAIN_SESSION and p.window == MAIN_WINDOW]


def _is_board(pane: PaneInfo) -> bool:
    return pane.role == ROLE_BOARD


def _live_board(panes: list[PaneInfo]) -> PaneId | None:
    return next((p.id for p in panes if _is_board(p) and not p.dead), None)


def _main_pane(panes: list[PaneInfo]) -> PaneId | None:
    return next((p.id for p in panes if not _is_board(p)), None)


def _geometry(tmux: Tmux) -> tuple[int, bool]:
    output = tmux.run(
        "display-message", "-p", "-t", MAIN_TARGET, "#{window_width}\t#{window_zoomed_flag}"
    )
    width, _, zoomed = output.partition("\t")
    if not width.isdigit() or zoomed not in {"0", "1"}:
        msg = f"window geometry {output!r}"
        raise UnreadableOutput(msg)
    return int(width), zoomed == "1"


def _require_layout(tmux: Tmux) -> Layout:
    layout = find_layout(tmux)
    if layout is None:
        raise UnreadableOutput(_NO_BOARD)
    return layout


def find_layout(tmux: Tmux) -> Layout | None:
    """Read the layout; None without a live dashboard in `meute:main`.

    Raises:
        CommandFailed: tmux failed.
        UnreadableOutput: tmux printed something unreadable.
    """
    panes = main_window_panes(tmux)
    board = _live_board(panes)
    if board is None:
        return None
    width, zoomed = _geometry(tmux)
    return Layout(board=board, main=_main_pane(panes), width=width, zoomed=zoomed)


def _create_pane(tmux: Tmux, args: list[str], command: tuple[str, ...], role: str) -> PaneId:
    pane = PaneId(tmux.run(*args, "-P", "-F", "#{pane_id}", "--", *command))
    set_pane_option(tmux, pane, ROLE_OPTION, role)
    return pane


def _split_board(tmux: Tmux, spec: LayoutSpec, target: PaneId) -> PaneId:
    args = ["split-window", "-h", "-l", str(spec.board_width), "-t", target]
    return _create_pane(tmux, args, spec.board_command, ROLE_BOARD)


def _create_session(tmux: Tmux, spec: LayoutSpec) -> None:
    args = ["new-session", "-d", "-s", MAIN_SESSION, "-n", MAIN_WINDOW, "-x", "200", "-y", "50"]
    welcome = _create_pane(tmux, args, spec.welcome_command, ROLE_WELCOME)
    select_pane(tmux, _split_board(tmux, spec, welcome))


def _recreate_main_window(tmux: Tmux, spec: LayoutSpec) -> None:
    args = ["new-window", "-d", "-t", f"={MAIN_SESSION}:", "-n", MAIN_WINDOW]
    welcome = _create_pane(tmux, args, spec.welcome_command, ROLE_WELCOME)
    _split_board(tmux, spec, welcome)


def _repair(tmux: Tmux, spec: LayoutSpec) -> None:
    panes = main_window_panes(tmux)
    main = _main_pane(panes)
    board = _live_board(panes)
    if board is None:
        anchor = main or (panes[0].id if panes else None)
        if anchor is None:
            _recreate_main_window(tmux, spec)
            return
        board = _split_board(tmux, spec, anchor)
    if main is None:
        args = ["split-window", "-h", "-b", "-t", board]
        _create_pane(tmux, args, spec.welcome_command, ROLE_WELCOME)
    for pane in panes:
        if _is_board(pane) and pane.dead:
            kill_pane(tmux, pane.id)


def ensure_layout(tmux: Tmux, spec: LayoutSpec) -> Layout:
    """Create or repair the layout, then apply the narrow mode.

    Raises:
        CommandFailed: tmux failed.
        UnreadableOutput: tmux printed something unreadable, or no dashboard exists afterwards.
    """
    if tmux.has_session(MAIN_SESSION):
        _repair(tmux, spec)
    else:
        _create_session(tmux, spec)
    layout = _require_layout(tmux)
    narrow = is_narrow(layout.width, spec.narrow_threshold)
    if narrow == layout.zoomed and narrow:
        return layout
    if narrow != layout.zoomed:
        tmux.run("resize-pane", "-Z", "-t", layout.board)
    if not narrow:
        tmux.run("resize-pane", "-t", layout.board, "-x", str(spec.board_width))
    return _require_layout(tmux)
