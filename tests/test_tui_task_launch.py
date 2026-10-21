"""`L` in the Tasks tab launches Claude on the task in a thread worker; the board stays usable."""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import TASKS_FOOTER, BoardAction, BoardData, LaunchOnTask
from meute.core.errors import InvalidInput, MeuteError, PromptNotPasted
from meute.core.task import TaskId
from meute.tui.board import BoardApp
from support import BOARD_HOME, NOW, at_due, make_task

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_NO_POLL = 3600.0
_LAUNCHING = "Launching Claude on #1…"
_DUE = at_due("2026-10-14T18:00[Europe/Paris]")  # undated tasks start folded


def _data() -> BoardData:
    return BoardData(
        sessions=(),
        repos=(),
        orphans=(),
        home=BOARD_HOME,
        now=NOW,
        tasks=(replace(make_task(1, due=_DUE), title="Review"), make_task(2, due=_DUE)),
    )


class BlockingBackend:
    """Blocks every action until released, and notes the thread it ran on."""

    def __init__(self) -> None:
        self.pending: BoardData | None = _data()
        self.actions: list[BoardAction] = []
        self.threads: list[int] = []
        self.release = threading.Event()
        self.perform_error: MeuteError | None = None
        self.unexpected: Exception | None = None  # a failure the backend never promised

    def load(self) -> BoardData | None:
        data, self.pending = self.pending, None
        return data

    def perform(self, action: BoardAction) -> None:
        self.actions.append(action)
        self.threads.append(threading.get_ident())
        assert self.release.wait(timeout=10)
        if self.unexpected is not None:
            raise self.unexpected
        if self.perform_error is not None:
            raise self.perform_error


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


async def _until(pilot: Pilot[None], condition: Callable[[], object], what: str) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, what
        await pilot.pause(0.01)


def _launch(backend: BlockingBackend, scenario: Scenario) -> None:
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press("tab", "L")
            await scenario(app, pilot)

    asyncio.run(run())


def test_launch_runs_in_a_worker_thread_and_says_so() -> None:
    backend = BlockingBackend()
    seen: list[str] = []

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the launch never started")
        seen.append(_footer(app))
        backend.pending = _data()
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == TASKS_FOOTER, "the launch never ended")
        assert backend.pending is None  # reread after the launch

    _launch(backend, scenario)
    assert seen == [_LAUNCHING]
    assert backend.actions == [LaunchOnTask(task_id=TaskId(1))]  # and nothing else: no status
    assert backend.threads != [threading.get_ident()]


def test_a_second_l_during_the_launch_is_ignored() -> None:
    backend = BlockingBackend()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: backend.actions, "the launch never started")
        await pilot.press("L")
        assert _footer(app) == _LAUNCHING
        backend.release.set()
        await _until(pilot, lambda: _footer(app) == TASKS_FOOTER, "the launch never ended")

    _launch(backend, scenario)
    assert backend.actions == [LaunchOnTask(task_id=TaskId(1))]


def test_claude_not_ready_says_the_prompt_was_not_pasted() -> None:
    backend = BlockingBackend()
    backend.perform_error = PromptNotPasted(TaskId(1), timeout_seconds=10)
    backend.release.set()
    expected = "#1: prompt not pasted (Claude not ready after 10 s)"

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: _footer(app) == expected, "no notice shown")

    _launch(backend, scenario)


def test_a_refused_launch_shows_its_error() -> None:
    backend = BlockingBackend()
    message = "#1 has no repository: set one on the task or its project"
    backend.perform_error = InvalidInput(message)
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: _footer(app) == f"Error: {message}", "no error shown")

    _launch(backend, scenario)


def test_an_unexpected_failure_ends_the_launch_with_its_error() -> None:
    backend = BlockingBackend()
    backend.unexpected = ValueError("boom")
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await _until(pilot, lambda: _footer(app) == "Error: boom", "no error shown")
        backend.unexpected = None
        await pilot.press("L")  # the failed launch was forgotten: a new one starts
        await _until(pilot, lambda: len(backend.actions) == 2, "no second launch")

    _launch(backend, scenario)
