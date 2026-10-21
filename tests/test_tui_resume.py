"""`r` resumes an ended Claude session in a worker; repeated keys send one action."""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    FOOTER,
    BoardAction,
    BoardData,
    ResumeSession,
    SessionRow,
    ended_text,
    error_text,
    resuming_text,
)
from meute.core.claude_session import ClaudeDetails
from meute.core.errors import MeuteError
from meute.core.session import AgentKind, Session
from meute.core.session_state import Running
from meute.tui.board import BoardApp
from support import BOARD_HOME, BOARD_ID_A, board_data, board_session

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_SIZE = (60, 30)
_NO_POLL = 3600.0


class BlockingBackend:
    """Blocks every action until released."""

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


def _claude(*, exited: bool, native_id: str | None = "abc") -> tuple[Session, BoardData]:
    base = board_session(BOARD_ID_A, "gone", BOARD_HOME / "git" / "gone", None, exited=exited)
    session = replace(base, agent=AgentKind.CLAUDE)
    if exited is False:
        session = replace(session, state=Running())
    details = {} if native_id is None else {BOARD_ID_A: ClaudeDetails(native_id=native_id)}
    data = replace(
        board_data(),
        sessions=(SessionRow(session=session, has_pane=False, displayed=False),),
        repos=(),
        orphans=(),
        details=details,
    )
    return session, data


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


async def _until(pilot: Pilot[None], condition: Callable[[], object], what: str) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, what
        await pilot.pause(0.01)


def _run(backend: BlockingBackend, keys: tuple[str, ...], scenario: Scenario) -> None:
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press(*keys)
            await scenario(app, pilot)

    asyncio.run(run())


def test_r_resumes_in_a_worker_and_the_footer_says_so() -> None:
    session, data = _claude(exited=True)
    backend = BlockingBackend(data)
    seen: list[str] = []

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the resume never started")
        seen.append(_footer(app))
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == FOOTER, "the resume never ended")

    _run(backend, ("e", "r"), scenario)
    assert seen == [resuming_text(session.title)]
    assert backend.actions == [ResumeSession(session_id=session.id)]
    assert backend.threads != [threading.get_ident()]


def test_r_twice_sends_one_action() -> None:
    _, data = _claude(exited=True)
    backend = BlockingBackend(data)

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the resume never started")
        await pilot.press("r")
        assert _footer(app) == resuming_text("gone")
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == FOOTER, "the resume never ended")

    _run(backend, ("e", "r"), scenario)
    assert len(backend.actions) == 1


def test_r_on_a_live_session_says_so_and_sends_nothing() -> None:
    _, data = _claude(exited=False)
    backend = BlockingBackend(data)

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == '"gone" is still running'

    _run(backend, ("r",), scenario)
    assert backend.actions == []


def test_r_without_a_native_id_says_why() -> None:
    _, data = _claude(exited=True, native_id=None)
    backend = BlockingBackend(data)

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == '"gone" cannot be resumed: Claude never confirmed its id'

    _run(backend, ("e", "r"), scenario)
    assert backend.actions == []


def test_a_failed_resume_shows_its_error() -> None:
    _, data = _claude(exited=True)
    backend = BlockingBackend(data)
    backend.perform_error = MeuteError("no such conversation")
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: _footer(app) == error_text("no such conversation"), "no error")

    _run(backend, ("e", "r"), scenario)


def test_enter_on_an_ended_claude_session_without_a_pane_points_to_r() -> None:
    _, data = _claude(exited=True)
    backend = BlockingBackend(data)

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == ended_text("gone", AgentKind.CLAUDE)
        assert _footer(app) == '"gone" has ended: r resumes · c starts a new session'

    _run(backend, ("e", "enter"), scenario)
    assert backend.actions == []
