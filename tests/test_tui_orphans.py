"""Enter, a and x on an orphan pane; repeated keys send one action."""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from dataclasses import replace

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    AdoptOrphan,
    BoardData,
    CloseOrphan,
    ShowPane,
)
from meute.core.orphans import (
    ORPHAN_FOOTER,
    Orphan,
    closing_text,
    confirm_close_text,
)
from meute.core.session import AgentKind
from meute.tui.board import BoardApp
from support import BlockingBackend, board_data, until

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]
_SIZE = (70, 20)
_NO_POLL = 3600.0
_ID = "11111111-1111-4111-8111-111111111111"
_VALID = Orphan(meute_id=_ID, pane_id="%7", command="claude", cwd="/srv/x", dead=False)
_HOSTILE = Orphan(meute_id="x;y", pane_id="%8", command="claude\x1b[2J", cwd="/srv", dead=False)


def _only(orphan: Orphan) -> BoardData:
    return replace(board_data(), sessions=(), repos=(), orphans=(orphan,))


def _footer(app: BoardApp) -> str:
    content = app.query_one("#footer", Static).content
    assert isinstance(content, Content)
    return content.plain


def _run(backend: BlockingBackend, keys: tuple[str, ...], scenario: Scenario) -> None:
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press(*keys)
            await scenario(app, pilot)

    asyncio.run(run())


def test_the_footer_on_an_orphan_lists_its_keys() -> None:
    backend = BlockingBackend(_only(_VALID))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == ORPHAN_FOOTER

    _run(backend, ("down",), scenario)


def test_enter_shows_the_pane() -> None:
    backend = BlockingBackend(_only(_VALID))
    backend.release.set()

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()

    _run(backend, ("down", "enter"), scenario)
    assert backend.actions == [ShowPane(pane_id="%7")]


def test_a_adopts_in_a_worker_and_twice_sends_one_action() -> None:
    backend = BlockingBackend(_only(_VALID))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: backend.actions, "the adoption never started")
        await pilot.press("a")
        await pilot.pause()
        backend.release.set()
        await until(pilot, lambda: _footer(app) == ORPHAN_FOOTER, "the adoption never ended")

    _run(backend, ("down", "a"), scenario)
    assert backend.actions == [AdoptOrphan(orphan=_VALID)]
    assert backend.threads != [threading.get_ident()]


def test_a_on_an_orphan_that_cannot_be_adopted_says_why() -> None:
    backend = BlockingBackend(_only(_HOSTILE))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == "not a meute id: only x closes it"

    _run(backend, ("down", "a"), scenario)
    assert backend.actions == []


def test_x_asks_and_any_other_key_cancels() -> None:
    backend = BlockingBackend(_only(_VALID))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()
        assert _footer(app) == confirm_close_text("claude")
        await pilot.press("n")
        assert _footer(app) == ORPHAN_FOOTER

    _run(backend, ("down", "x"), scenario)
    assert backend.actions == []


def test_x_y_closes_in_a_worker_and_a_during_the_close_is_ignored() -> None:
    backend = BlockingBackend(_only(_VALID))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: backend.actions, "the close never started")
        assert _footer(app) == closing_text("claude")
        await pilot.press("a", "x", "y")
        await pilot.pause()
        assert _footer(app) == closing_text("claude")
        backend.release.set()
        await until(pilot, lambda: _footer(app) == ORPHAN_FOOTER, "the close never ended")

    _run(backend, ("down", "x", "y"), scenario)
    assert backend.actions == [CloseOrphan(meute_id=_ID, agent=AgentKind.CLAUDE)]
    assert backend.threads != [threading.get_ident()]


def test_x_y_closes_an_orphan_whose_identifier_is_not_one() -> None:
    backend = BlockingBackend(_only(_HOSTILE))
    backend.release.set()

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await until(pilot, lambda: backend.actions, "the close never started")

    _run(backend, ("down", "x", "y"), scenario)
    assert backend.actions == [CloseOrphan(meute_id="x;y", agent=AgentKind.BASH)]


def test_a_on_a_repository_does_nothing() -> None:
    backend = BlockingBackend(replace(board_data(), orphans=()))

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.pause()

    _run(backend, ("down", "down", "down", "down", "a"), scenario)
    assert backend.actions == []


def test_a_filters_on_a_session_and_adopts_on_an_orphan() -> None:
    data = replace(board_data(), orphans=(_VALID,))
    backend = BlockingBackend(data)
    backend.release.set()
    seen: list[bool] = []

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        board = app.query_one("#board", Static).content
        assert isinstance(board, Content)
        seen.append("build" in board.plain)
        await pilot.press("a")  # a session is selected: the attention filter
        board = app.query_one("#board", Static).content
        assert isinstance(board, Content)
        seen.append("build" in board.plain)
        assert backend.actions == []
        await pilot.press("a")  # back to the full view
        await pilot.press(*["down"] * 8, "a")  # the orphan, the last selectable line
        await until(pilot, lambda: backend.actions, "the adoption never started")

    _run(backend, ("down",), scenario)
    assert seen == [True, False]
    assert backend.actions == [AdoptOrphan(orphan=_VALID)]
