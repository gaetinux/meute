"""A task picked in the launch form launches like `L`: in a worker, the form kept meanwhile."""

import asyncio
import threading
from collections.abc import Awaitable, Callable

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import LaunchBash, LaunchClaude
from meute.core.errors import InvalidInput, PromptNotPasted
from meute.core.project import RepoId
from meute.core.task import TaskId
from meute.tui.board import BoardApp, BoardOptions
from support import BlockingBackend, until
from test_tui_launch_form import _MEUTE, _data  # pyright: ignore[reportPrivateUsage] — reused

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_NO_POLL = 3600.0
_SIZE = (72, 30)
_LAUNCHING = "Launching Claude on #2…"
# The Title field, "mine" typed, then the Task field: the second task is picked.
_PICK = ("N", "tab", "tab", "tab", "tab", "m", "i", "n", "e", "tab", "right")


def _text(app: BoardApp, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content.plain


def _is_open(app: BoardApp) -> bool:
    return app.query_one("#launch-form", Static).display


def _run(backend: BlockingBackend, keys: tuple[str, ...], scenario: Scenario) -> None:
    app = BoardApp(backend, BoardOptions(permission_mode="auto"), poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            await pilot.press(*keys)
            await scenario(app, pilot)

    asyncio.run(run())


_EXPECTED = LaunchClaude(
    cwd=_MEUTE, repo_id=RepoId(1), title="mine", task_id=TaskId(2), permission_mode="auto"
)


def test_a_picked_task_is_launched_in_a_worker_and_the_form_waits() -> None:
    backend = BlockingBackend(_data())

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: backend.actions, "the launch never started")
        await pilot.pause()
        assert _is_open(app)  # kept while Claude starts
        assert _text(app, "footer") == _LAUNCHING
        backend.release.set()
        await until(pilot, lambda: not _is_open(app), "the form never closed")

    _run(backend, (*_PICK, "enter"), scenario)
    assert backend.actions == [_EXPECTED]
    assert backend.threads != [threading.get_ident()]


def test_a_second_enter_during_the_launch_is_ignored() -> None:
    backend = BlockingBackend(_data())

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: backend.actions, "the launch never started")
        await pilot.press("enter", "x", "enter")
        await pilot.pause(0.05)
        assert _is_open(app)
        backend.release.set()
        await until(pilot, lambda: not _is_open(app), "the form never closed")

    _run(backend, (*_PICK, "enter"), scenario)
    assert backend.actions == [_EXPECTED]


def test_a_failed_task_launch_keeps_the_form_its_text_and_the_error() -> None:
    backend = BlockingBackend(_data())
    backend.perform_error = InvalidInput("folder not found: /x")
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(
            pilot, lambda: "Error: folder not found: /x" in _text(app, "launch-form"), "no error"
        )
        assert _is_open(app)
        assert "mine" in _text(app, "launch-form")
        backend.perform_error = None
        await pilot.press("enter")  # the same form, launched again
        await until(pilot, lambda: not _is_open(app), "the form never closed")

    _run(backend, (*_PICK, "enter"), scenario)
    assert backend.actions == [_EXPECTED, _EXPECTED]


def test_claude_not_ready_closes_the_form_and_says_so() -> None:
    backend = BlockingBackend(_data())
    backend.perform_error = PromptNotPasted(TaskId(2), timeout_seconds=10)
    backend.release.set()
    expected = "#2: prompt not pasted (Claude not ready after 10 s)"

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: _text(app, "footer") == expected, "no notice shown")
        assert not _is_open(app)

    _run(backend, (*_PICK, "enter"), scenario)


def test_a_launch_without_a_task_stays_on_the_app_thread() -> None:
    backend = BlockingBackend(_data())
    backend.release.set()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert not _is_open(app)

    _run(backend, ("N", "right", "enter"), scenario)
    assert backend.actions == [LaunchBash(cwd=_MEUTE, repo_id=RepoId(1))]
    assert backend.threads == [threading.get_ident()]
