"""The board's one-line footer and its full list of keys behind `?` (spec 5.6)."""

import asyncio

from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import FOOTER, KEYS_HELP
from meute.tui.board import BoardApp
from support import board_data
from test_tui_board import FakeBackend

_SIZE = (60, 30)
_NO_POLL = 3600.0


def _footers(*keys: str) -> list[str]:
    """Press each key on a fresh board and return the footer text after each one."""
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    footers: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            for key in keys:
                await pilot.press(key)
                content = app.query_one("#footer", Static).content
                assert isinstance(content, Content)
                footers.append(content.plain)

    asyncio.run(scenario())
    return footers


def test_footer_holds_on_one_line_of_the_default_board() -> None:
    assert FOOTER == "↑↓ select · Enter show · c/n new · x stop · ? keys"
    assert len(FOOTER) <= 58  # 60 columns minus the scroll bar's room


def test_keys_help_lists_every_key() -> None:
    for key in ("↑↓", "Enter", "Space", "c ", "n ", "x ", "a ", "e ", "Tab ", "q ", "Esc"):
        assert key in KEYS_HELP
    assert all(len(line) <= 58 for line in KEYS_HELP.splitlines())


def test_question_mark_toggles_the_keys_help() -> None:
    assert _footers("question_mark", "question_mark") == [KEYS_HELP, FOOTER]


def test_escape_closes_the_keys_help() -> None:
    assert _footers("question_mark", "escape") == [KEYS_HELP, FOOTER]


def test_keys_still_work_while_the_help_is_open() -> None:
    footers = _footers("question_mark", "x")
    assert footers[1].startswith("Stop ")
