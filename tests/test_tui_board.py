"""Tests of the Textual dashboard: behaviour through Pilot, rendering through SVG snapshots."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import replace
from pathlib import Path
from typing import Protocol

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_sessions import board_sessions
from meute.core.board_view import (
    FOOTER,
    BoardAction,
    BoardData,
    LaunchBash,
    LaunchClaude,
    SessionRow,
    ShowSession,
    StopSession,
    confirm_stop_text,
    error_text,
    repo_line,
)
from meute.core.errors import MeuteError
from meute.core.project import RepoId
from meute.core.repo import Repo
from meute.core.session import SessionId
from meute.core.sessions_view import SessionLine, ViewState
from meute.tui.board import BoardApp
from meute.tui.sessions_pane import SELECTED_STYLE
from support import (
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    BOARD_REPO_1,
    BOARD_REPO_2,
    BOARD_SESSION_B,
    board_data,
    board_repo,
    board_session,
    selected_row,
)

_SIZE = (60, 30)
_NO_POLL = 3600.0  # the timer never fires: only the load at mount happens


class SnapCompare(Protocol):
    """The `snap_compare` fixture of pytest-textual-snapshot, typed for our use."""

    def __call__(
        self,
        app: BoardApp,
        *,
        press: Iterable[str] = (),
        terminal_size: tuple[int, int] = (80, 24),
        run_before: Callable[[Pilot[None]], Awaitable[None] | None] | None = None,
    ) -> bool: ...


class FakeBackend:
    """Hands out `pending` once (then `None`: nothing new), records the actions, can fail."""

    def __init__(self, data: BoardData | None = None) -> None:
        self.pending = data
        self.actions: list[BoardAction] = []
        self.load_error: MeuteError | None = None
        self.perform_error: MeuteError | None = None

    def load(self) -> BoardData | None:
        if self.load_error is not None:
            raise self.load_error
        data, self.pending = self.pending, None
        return data

    def perform(self, action: BoardAction) -> None:
        self.actions.append(action)  # every attempt, failed ones included
        if self.perform_error is not None:
            raise self.perform_error


def _content(app: BoardApp, widget_id: str) -> Content:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content


def _highlighted(app: BoardApp) -> list[str]:
    """The selected line (the first of a card), without the padding that fills its background."""
    return [row.rstrip() for row in selected_row(_content(app, "board"), (SELECTED_STYLE,))]


def _run(backend: FakeBackend, *keys: str) -> str:
    """Press `keys` on a fresh board and return the footer text shown afterwards."""
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    footer: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press(*keys)
            footer.append(_content(app, "footer").plain)

    asyncio.run(scenario())
    return footer[0]


async def _reload(pilot: Pilot[None], backend: FakeBackend, data: BoardData) -> None:
    """Wait for the board's timer to load `data`."""
    deadline = time.monotonic() + 10
    backend.pending = data
    while backend.pending is data:
        assert time.monotonic() < deadline, "the board never reloaded"
        await pilot.pause(0.01)


def _view_texts(data: BoardData) -> list[str]:
    return [line.text for line in board_sessions(data, ViewState(), _SIZE[0]).view.lines]


def _session_text(data: BoardData, session_id: SessionId) -> str:
    lines = board_sessions(data, ViewState(), _SIZE[0]).view.lines
    return next(x.text for x in lines if isinstance(x, SessionLine) and x.session_id == session_id)


def _repo_text(repo: Repo) -> str:
    return f"  {repo_line(repo)}"


def test_board_shows_the_view_model_lines_and_highlights_the_first_entry() -> None:
    data = board_data()
    app = BoardApp(FakeBackend(data), poll_seconds=_NO_POLL)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE):
            rows = _content(app, "board").plain.split("\n")
            assert [row.rstrip() for row in rows] == [t.rstrip() for t in _view_texts(data)]
            assert _highlighted(app) == [_session_text(data, BOARD_ID_A)]
            assert _content(app, "footer").plain == FOOTER

    asyncio.run(scenario())


def test_enter_on_session_shows_it() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "down", "enter")
    assert backend.actions == [ShowSession(session_id=BOARD_ID_B)]


def test_enter_and_n_on_repo_launch_bash_there() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "j", "j", "enter", "n", "j", "n")
    assert backend.actions == [
        LaunchBash(cwd=BOARD_REPO_1.path, repo_id=RepoId(1)),
        LaunchClaude(cwd=BOARD_REPO_1.path, repo_id=RepoId(1)),
        LaunchClaude(cwd=BOARD_REPO_2.path, repo_id=RepoId(2)),
    ]


def test_n_on_session_launches_in_its_cwd() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "down", "n")
    assert backend.actions == [LaunchBash(cwd=Path("/srv/work"), repo_id=None)]


def test_x_then_y_stops() -> None:
    asking = FakeBackend(board_data())
    assert _run(asking, "down", "x") == confirm_stop_text(BOARD_SESSION_B.title)
    assert asking.actions == []
    backend = FakeBackend(board_data())
    assert _run(backend, "down", "x", "y") == FOOTER
    assert backend.actions == [StopSession(session_id=BOARD_ID_B)]


def test_x_then_other_key_cancels() -> None:
    backend = FakeBackend(board_data())
    assert _run(backend, "x", "n") == FOOTER
    assert backend.actions == []
    backend = FakeBackend(board_data())
    assert _run(backend, "x", "enter", "y") == FOOTER
    assert backend.actions == []


def test_x_on_repo_does_nothing() -> None:
    backend = FakeBackend(board_data())
    assert _run(backend, "j", "j", "x") == FOOTER
    backend.pending = board_data()
    assert _run(backend, "j", "j", "x", "y") == FOOTER
    assert backend.actions == []


def test_navigation_is_bounded() -> None:
    backend = FakeBackend(board_data())
    _ = _run(backend, "up", "k", "enter", *["down"] * 6, "enter", "k", "enter")
    assert backend.actions == [
        ShowSession(session_id=BOARD_ID_A),
        LaunchBash(cwd=BOARD_REPO_2.path, repo_id=RepoId(2)),
        LaunchBash(cwd=BOARD_REPO_1.path, repo_id=RepoId(1)),
    ]


def test_selection_survives_reordering() -> None:
    first = board_data()
    backend = FakeBackend(first)
    app = BoardApp(backend, poll_seconds=0.01)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            reordered = replace(first, sessions=(first.sessions[1], first.sessions[0]))
            await _reload(pilot, backend, reordered)
            await pilot.press("enter")
            assert _highlighted(app) == [_session_text(first, BOARD_ID_A)]

    asyncio.run(scenario())
    assert backend.actions == [ShowSession(session_id=BOARD_ID_A)]


def test_selection_is_bounded_when_its_entry_disappears() -> None:
    first = board_data()
    backend = FakeBackend(first)
    app = BoardApp(backend, poll_seconds=0.01)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("j", "j", "j")
            await _reload(pilot, backend, replace(first, repos=(BOARD_REPO_1,)))
            await pilot.press("enter")

    asyncio.run(scenario())
    assert backend.actions == [LaunchBash(cwd=BOARD_REPO_1.path, repo_id=RepoId(1))]


def test_poll_after_the_widgets_are_gone_does_not_crash() -> None:
    # On quit, Textual removes the widgets before it stops the app's timers.
    backend = FakeBackend(board_data())
    app = BoardApp(backend, poll_seconds=0.01)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await app.query("#board, #footer").remove()
            await _reload(pilot, backend, board_data())

    asyncio.run(scenario())


def _highlighted_after(data: BoardData, *keys: str) -> list[str]:
    app = BoardApp(FakeBackend(data), poll_seconds=_NO_POLL)
    highlighted: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press(*keys)
            highlighted.extend(_highlighted(app))

    asyncio.run(scenario())
    return highlighted


def test_highlight_reaches_each_repository() -> None:
    assert _highlighted_after(board_data(), "j", "j") == [_repo_text(BOARD_REPO_1)]
    assert _highlighted_after(board_data(), "j", "j", "j") == [_repo_text(BOARD_REPO_2)]


def test_highlight_skips_the_no_sessions_placeholder() -> None:
    data = replace(board_data(), sessions=())
    assert _highlighted_after(data) == [_repo_text(BOARD_REPO_1)]
    assert _highlighted_after(data, "j") == [_repo_text(BOARD_REPO_2)]


def test_enter_after_an_error_clears_it_and_acts_again() -> None:
    backend = FakeBackend(board_data())
    backend.perform_error = MeuteError("db locked")
    assert _run(backend, "enter", "enter") == error_text("db locked")
    # The second Enter reached the backend: dismissing the error does not swallow the key.
    assert backend.actions == [ShowSession(session_id=BOARD_ID_A)] * 2


def test_backend_error_is_shown_until_next_key() -> None:
    backend = FakeBackend(board_data())
    backend.perform_error = MeuteError("db locked")
    assert _run(backend, "enter") == error_text("db locked")
    backend.pending = board_data()
    assert _run(backend, "enter", "down") == FOOTER


def test_load_error_is_shown() -> None:
    backend = FakeBackend()
    backend.load_error = MeuteError("database is locked")
    assert _run(backend) == error_text("database is locked")


def test_brackets_in_data_are_shown_literally() -> None:
    title = "[wip] fix [/]"
    session = board_session(BOARD_ID_A, title, BOARD_HOME / "[red]", None, exited=False)
    repo = board_repo(1, "[bold]x", None)
    data = BoardData(
        sessions=(SessionRow(session=session, has_pane=True, displayed=False),),
        repos=(repo,),
        orphans=("[link=x]",),
        home=BOARD_HOME,
    )
    backend = FakeBackend(data)
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("x")
            assert _content(app, "footer").plain == confirm_stop_text(title)
            shown = [
                widget.render_line(y).text
                for widget in app.query(Static)
                for y in range(widget.size.height)
            ]
            screen = "\n".join(shown)
            for text in (title, "[bold]x", "[link=x]", "~/[red]", confirm_stop_text(title)):
                assert text in screen

    asyncio.run(scenario())


def _board(data: BoardData | None = None) -> BoardApp:
    return BoardApp(FakeBackend(board_data() if data is None else data), poll_seconds=_NO_POLL)


def test_board_60_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_board(), terminal_size=(60, 30))


def test_board_100_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_board(), terminal_size=(100, 30))


def test_board_empty(snap_compare: SnapCompare) -> None:
    empty = BoardData(sessions=(), repos=(), orphans=(), home=None)
    assert snap_compare(_board(empty), terminal_size=(60, 30))


def test_board_confirming_stop(snap_compare: SnapCompare) -> None:
    assert snap_compare(_board(), press=["down", "x"], terminal_size=(60, 30))


def test_board_with_error(snap_compare: SnapCompare) -> None:
    backend = FakeBackend()
    backend.load_error = MeuteError("database is locked")
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    assert snap_compare(app, terminal_size=(60, 30))
