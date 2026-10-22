"""`r` on a session whose stop still runs is ignored: one action at a time per session."""

import asyncio
import time
from collections.abc import Callable

from textual.pilot import Pilot

from meute.core.board_view import ResumeSession, StopSession, stopping_text
from meute.tui.board import BoardApp
from test_tui_resume import (
    BlockingBackend,
    _claude,  # pyright: ignore[reportPrivateUsage] — helper reused
    _footer,  # pyright: ignore[reportPrivateUsage] — helper reused
)

_SIZE = (60, 30)
_POLL = 0.01


async def _until(pilot: Pilot[None], condition: Callable[[], object], what: str) -> None:
    deadline = time.monotonic() + 10
    while not condition():
        assert time.monotonic() < deadline, what
        await pilot.pause(0.01)


def _while_stopping(resume: Callable[[BoardApp, Pilot[None]], object]) -> BlockingBackend:
    """Stop the live session, let a reread show it ended, then try to resume it."""
    _, live = _claude(exited=False)
    session, ended = _claude(exited=True)
    backend = BlockingBackend(live)
    app = BoardApp(backend, poll_seconds=_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            await pilot.press("x", "y")
            await _until(pilot, lambda: backend.actions, "the stop never started")
            backend.pending = ended
            await _until(pilot, lambda: backend.pending is None, "the board never reloaded")
            await pilot.press("e")
            assert _footer(app) == stopping_text(session.title)
            result = resume(app, pilot)
            if asyncio.iscoroutine(result):
                await result
            await pilot.pause(0.1)
            backend.release.set()
            await _until(pilot, lambda: _footer(app) != stopping_text(session.title), "no end")

    asyncio.run(run())
    return backend


def test_r_during_the_stop_of_the_same_session_is_ignored() -> None:
    backend = _while_stopping(lambda _app, pilot: pilot.press("r"))
    assert [type(action) for action in backend.actions] == [StopSession]


def test_the_workers_ignore_a_resume_while_its_stop_runs() -> None:
    session, _ = _claude(exited=True)

    def resume(app: BoardApp, _pilot: Pilot[None]) -> None:
        app._background.resume(session)  # noqa: SLF001 — the guard itself  # pyright: ignore[reportPrivateUsage] — the guard itself

    backend = _while_stopping(resume)
    assert not any(isinstance(action, ResumeSession) for action in backend.actions)
