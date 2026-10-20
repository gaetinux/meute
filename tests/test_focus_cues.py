"""Where the focus is shows at a glance: tmux greys the inactive pane, the board dims itself."""

import asyncio
from pathlib import Path

from textual import events
from textual.content import Content
from textual.widgets import Static

from meute.core.styled import Role
from meute.tmux.conf import render_config
from meute.tui.board import BoardApp
from meute.tui.sessions_pane import (
    BLURRED_SELECTED_STYLE,
    ROLE_STYLES,
    SELECTED_STYLE,
)
from support import board_data
from test_tmux_conf import make_spec
from test_tui_board import FakeBackend
from tmux_support import TestServer

_SIZE = (60, 30)
_NO_POLL = 3600.0


def test_tmux_forwards_focus_and_greys_the_inactive_pane(
    tmux_server: TestServer, tmp_path: Path
) -> None:
    tmux = tmux_server.tmux
    conf = tmp_path / "tmux.conf"
    conf.write_text(render_config(make_spec(("meute",))))
    tmux.run("source-file", str(conf))
    assert tmux.run("show-options", "-gv", "focus-events").strip() == "on"
    assert tmux.run("show-options", "-gwv", "window-style").strip() == "bg=colour234"
    assert tmux.run("show-options", "-gwv", "window-active-style").strip() == "default"


def _styles(app: BoardApp) -> tuple[set[str], set[str]]:
    """Return the styles of the title and of the board's spans."""
    title = app.query_one("#title", Static).content
    board = app.query_one("#board", Static).content
    assert isinstance(title, Content)
    assert isinstance(board, Content)
    return {str(s.style) for s in title.spans}, {str(s.style) for s in board.spans}


def test_board_shows_whether_it_has_the_focus() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    seen: list[tuple[str, set[str], set[str]]] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            title = app.query_one("#title", Static).content
            assert isinstance(title, Content)
            seen.append((title.plain, *_styles(app)))
            app.post_message(events.AppBlur())
            await pilot.pause()
            seen.append((title.plain, *_styles(app)))
            app.post_message(events.AppFocus())
            await pilot.pause()
            seen.append((title.plain, *_styles(app)))

    asyncio.run(scenario())
    focused, blurred, back = seen
    assert focused[0].startswith(" Sessions  Tasks ")
    assert ROLE_STYLES[Role.TAB_ACTIVE] in focused[1]
    assert SELECTED_STYLE in focused[2]
    assert ROLE_STYLES[Role.TAB_ACTIVE] not in blurred[1]
    assert f"{ROLE_STYLES[Role.TAB]} underline" in blurred[1]
    assert BLURRED_SELECTED_STYLE in blurred[2]
    assert SELECTED_STYLE not in blurred[2]
    assert back == focused
