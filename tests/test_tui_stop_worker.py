"""The board stops a session in a thread worker: the dashboard stays responsive meanwhile."""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    FOOTER,
    BoardAction,
    BoardData,
    StopSession,
    error_text,
    stopping_text,
)
from meute.core.errors import MeuteError
from meute.tui.board import BoardApp
from support import BOARD_ID_B, BOARD_SESSION_B, board_data

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_SIZE = (60, 30)
_NO_POLL = 3600.0


class BlockingBackend:
    """Blocks a StopSession until released, and notes the thread it ran on."""

    def __init__(self, data: BoardData) -> None:
        self.pending: BoardData | None = data
        self.actions: list[BoardAction] = []
        self.threads: list[int] = []
        self.release = threading.Event()
        self.perform_error: MeuteError | None = None

    def load(self) -> BoardData | None:
        data, self.pending = self.pending, None
        return data

    def perform(self, action: BoardAction) -> None:
        self.actions.append(action)
        self.threads.append(threading.get_ident())
        assert self.release.wait(timeout=10)
        if self.perform_error is not None:
            raise self.perform_error


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


def _spans(app: BoardApp) -> list[tuple[int, int]]:
    content = app.query_one("#board", Static).content
    assert isinstance(content, Content)
    return [(span.start, span.end) for span in content.spans]


async def _until(pilot: Pilot[None], condition: Callable[[], object], what: str) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, what
        await pilot.pause(0.01)


def _stop_b(backend: BlockingBackend, scenario: Scenario) -> None:
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("down", "x", "y")
            await scenario(app, pilot)

    asyncio.run(run())


def test_stop_runs_in_a_worker_thread_and_the_board_stays_responsive() -> None:
    backend = BlockingBackend(board_data())
    seen: list[str] = []

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the stop never started")
        seen.append(_footer(app))
        before = _spans(app)
        await pilot.press("j")  # handled while the stop is still blocked
        assert _spans(app) != before
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == FOOTER, "the stop never ended")

    _stop_b(backend, scenario)
    assert seen == [stopping_text(BOARD_SESSION_B.title)]
    assert backend.actions == [StopSession(session_id=BOARD_ID_B)]
    assert backend.threads != [threading.get_ident()]


def test_second_x_on_the_session_being_stopped_is_ignored() -> None:
    backend = BlockingBackend(board_data())

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the stop never started")
        await pilot.press("up", "down", "x", "y")
        assert _footer(app) == stopping_text(BOARD_SESSION_B.title)
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == FOOTER, "the stop never ended")

    _stop_b(backend, scenario)
    assert backend.actions == [StopSession(session_id=BOARD_ID_B)]


def test_a_failed_stop_shows_its_error() -> None:
    backend = BlockingBackend(board_data())
    backend.perform_error = MeuteError("tmux is gone")
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: _footer(app) == error_text("tmux is gone"), "no error shown")

    _stop_b(backend, scenario)


def test_the_end_of_a_stop_rereads_the_data() -> None:
    backend = BlockingBackend(board_data())

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the stop never started")
        backend.pending = board_data()
        backend.release.set()
        await _until(pilot, lambda: backend.pending is None, "no reread after the stop")

    _stop_b(backend, scenario)
