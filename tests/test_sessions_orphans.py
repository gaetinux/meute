"""Orphan panes in the Sessions view: selectable lines, kept across reads, folded as a section."""

import asyncio
from dataclasses import replace

import pytest
from textual.content import Content
from textual.widgets import Static

from meute.core.board_sessions import BoardSessions, board_sessions, line_entry
from meute.core.board_view import FOOTER, OrphanEntry
from meute.core.orphans import ORPHAN_KEYS, Orphan
from meute.core.sessions_view import (
    OrphanLine,
    ViewState,
    keep_selection,
    line_key,
    selectable,
    with_fold,
)
from meute.tui.board import BoardApp
from support import BOARD_HOME, board_data
from test_tui_board import FakeBackend

_ORPHAN = Orphan(
    meute_id="ghost", pane_id="%7", command="claude", cwd=str(BOARD_HOME / "git"), dead=False
)
_HOSTILE = Orphan(
    meute_id="x\x1b[2Jy", pane_id="%8", command="claude\x1b[2J", cwd="/w\nrk;", dead=True
)


def _board(*orphans: Orphan, state: ViewState | None = None) -> BoardSessions:
    return board_sessions(replace(board_data(), orphans=orphans), state or ViewState())


def _orphan_indexes(board: BoardSessions) -> list[int]:
    return [i for i, line in enumerate(board.view.lines) if isinstance(line, OrphanLine)]


def test_an_orphan_line_is_selectable_and_gives_its_entry() -> None:
    board = _board(_ORPHAN)
    (index,) = _orphan_indexes(board)
    assert index in selectable(board.view)
    assert line_key(board.view.lines[index]) == "orphan:ghost"
    assert board.view.lines[index].text == "  ? claude  ~/git  orphan"
    assert line_entry(board, index) == OrphanEntry(orphan=_ORPHAN)


def test_the_selection_keeps_the_orphan_after_a_read() -> None:
    before = _board(_ORPHAN)
    (index,) = _orphan_indexes(before)
    after = _board(_HOSTILE, _ORPHAN)
    kept = keep_selection("orphan:ghost", after.view, 0)
    assert kept == _orphan_indexes(after)[1]
    assert index != kept


def test_the_orphans_section_folds() -> None:
    state = with_fold(ViewState(), "section:Orphans", fold=True)
    board = _board(_ORPHAN, state=state)
    assert _orphan_indexes(board) == []
    assert board.view.lines[-1].text == "▶ Orphans (1)"


def test_hostile_orphan_data_is_one_line_without_control_characters() -> None:
    board = _board(_HOSTILE)
    (index,) = _orphan_indexes(board)
    text = board.view.lines[index].text
    assert all(char.isprintable() for char in text)
    assert line_key(board.view.lines[index]) == f"orphan:{_HOSTILE.meute_id}"


def _press(key: str) -> tuple[FakeBackend, str]:
    data = replace(board_data(), sessions=(), repos=(), ended=(), orphans=(_ORPHAN,))
    backend = FakeBackend(data)
    app = BoardApp(backend, poll_seconds=3600.0)
    footer: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=(60, 30)) as pilot:
            await pilot.press(key)
            content = app.query_one("#footer", Static).content
            assert isinstance(content, Content)
            footer.append(content.plain)

    asyncio.run(scenario())
    return backend, footer[0]


@pytest.mark.parametrize("key", ["c", "n", "r"])
def test_session_keys_on_an_orphan_name_its_keys_and_launch_nothing(key: str) -> None:
    backend, footer = _press(key)
    assert (backend.actions, footer) == ([], ORPHAN_KEYS)


@pytest.mark.parametrize("key", ["enter", "x"])
def test_enter_and_x_on_an_orphan_do_nothing_yet(key: str) -> None:
    backend, footer = _press(key)
    assert (backend.actions, footer) == ([], FOOTER)
