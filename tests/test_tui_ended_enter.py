"""Enter or a click on an ended session without a pane explains itself instead of failing."""

import asyncio
from dataclasses import replace

from textual.content import Content
from textual.widgets import Static

from meute.core.board_sessions import board_sessions
from meute.core.board_view import BoardData, SessionRow, ShowSession, ended_text
from meute.core.sessions_view import SessionLine, ViewState
from meute.tui.board import BoardApp
from support import BOARD_HOME, BOARD_ID_A, board_data, board_session
from test_tui_board import FakeBackend

_SIZE = (60, 30)
_NO_POLL = 3600.0


def test_ended_text_names_the_session_and_the_way_out() -> None:
    assert ended_text("old") == '"old" has ended: c starts a new Claude session here'
    assert ended_text("a\x1bb") == '"a\ufffdb" has ended: c starts a new Claude session here'


def _data(*, has_pane: bool) -> BoardData:
    gone = board_session(BOARD_ID_A, "gone", BOARD_HOME / "git" / "gone", None, exited=True)
    return replace(
        board_data(),
        sessions=(SessionRow(session=gone, has_pane=has_pane, displayed=False),),
        repos=(),
        orphans=(),
        ended=(),
    )


def _after(data: BoardData, *, click: bool) -> tuple[FakeBackend, str]:
    backend = FakeBackend(data)
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    footer: list[str] = []
    lines = board_sessions(data, ViewState(show_ended=True)).view.lines

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("e")
            if click:
                y = next(i for i, x in enumerate(lines) if isinstance(x, SessionLine))
                _ = await pilot.click("#board", offset=(2, y))
            else:
                await pilot.press("enter")
            content = app.query_one("#footer", Static).content
            assert isinstance(content, Content)
            footer.append(content.plain)

    asyncio.run(scenario())
    return backend, footer[0]


def test_enter_on_an_ended_session_without_a_pane_explains() -> None:
    backend, footer = _after(_data(has_pane=False), click=False)
    assert backend.actions == []
    assert footer == ended_text("gone")


def test_click_on_an_ended_session_without_a_pane_explains() -> None:
    backend, footer = _after(_data(has_pane=False), click=True)
    assert backend.actions == []
    assert footer == ended_text("gone")


def test_an_ended_session_that_kept_its_pane_still_shows() -> None:
    backend, _ = _after(_data(has_pane=True), click=False)
    assert backend.actions == [ShowSession(session_id=BOARD_ID_A)]
