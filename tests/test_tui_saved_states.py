"""`S` saves the open sessions; `O` lists the saved states above the footer to reopen one."""

import asyncio
import threading
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    FOOTER,
    KEYS_HELP,
    BoardAction,
    BoardData,
    ReopenState,
    SaveState,
    StopSession,
)
from meute.core.errors import ActionNotice
from meute.core.saved_state import (
    LAST,
    SavedSession,
    SavedState,
    reopening_text,
    saved_text,
    state_line,
)
from meute.core.session import AgentKind
from meute.tui.board import BoardApp
from support import BOARD_AT, BOARD_ID_A, BOARD_ID_B, board_data, until
from test_tui_board import FakeBackend, SnapCompare

_SIZE = (60, 30)
_NO_POLL = 3600.0
_SAVED = "state saved: 2026-10-18 11:00"
_REPORT = "reopened 2 · skipped 1"


def _session(n: int) -> SavedSession:
    return SavedSession(
        session_id=BOARD_ID_A if n == 1 else BOARD_ID_B,
        agent=AgentKind.BASH,
        cwd=Path("/srv/work"),
        native_id=None,
        title=f"shell {n}",
        task_id=None,
        repo_id=None,
        displayed=False,
    )


def _state(name: str, count: int, minutes: int) -> SavedState:
    return SavedState(
        name=name,
        created_at=BOARD_AT - timedelta(minutes=minutes),
        sessions=tuple(_session(1 + n % 2) for n in range(count)),
    )


_STATES = (_state(LAST, 2, 5), _state("morning", 1, 120), _state("monday", 3, 3000))


def _data(states: tuple[SavedState, ...] = _STATES) -> BoardData:
    return replace(board_data(), now=BOARD_AT, saved_states=states)


class StatesBackend(FakeBackend):
    """Tells what a save and a reopening tell; a reopening waits for `release`."""

    def __init__(self, data: BoardData) -> None:
        super().__init__(data)
        self.release = threading.Event()
        self.release.set()

    def perform(self, action: BoardAction) -> None:
        super().perform(action)
        if isinstance(action, SaveState):
            raise ActionNotice(_SAVED)
        if isinstance(action, ReopenState):
            assert self.release.wait(timeout=10)
            raise ActionNotice(_REPORT)


def _text(app: BoardApp, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content.plain


def _panel(app: BoardApp) -> list[str] | None:
    """The panel's lines below its rule, or `None` while it is hidden."""
    if not app.query_one("#saved-states", Static).display:
        return None
    return [line.rstrip() for line in _text(app, "saved-states").splitlines()[1:]]


def _run(backend: StatesBackend, *keys: str) -> tuple[str, list[str] | None]:
    """Press `keys` on a fresh board, wait for any reopening to end: the footer and the panel."""
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    seen: list[tuple[str, list[str] | None]] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press(*keys)
            await until(pilot, lambda: not _text(app, "footer").startswith("reopening"), "busy")
            await pilot.pause()
            seen.append((_text(app, "footer"), _panel(app)))

    asyncio.run(scenario())
    return seen[0]


def test_s_saves_the_open_sessions_and_tells_the_name() -> None:
    backend = StatesBackend(_data())
    footer, _ = _run(backend, "S")
    assert backend.actions == [SaveState()]
    assert footer == _SAVED


def test_the_panel_is_hidden_until_o() -> None:
    _, panel = _run(StatesBackend(_data()))
    assert panel is None


def test_o_lists_last_first_then_the_other_states() -> None:
    backend = StatesBackend(_data())
    _, panel = _run(backend, "O")
    assert panel == [
        "last  2 sessions  5m",
        "morning  1 session  2h",
        "monday  3 sessions  2d",
    ]
    assert panel == [state_line(state, BOARD_AT) for state in _STATES]
    assert backend.actions == []


def test_enter_reopens_the_selected_state() -> None:
    backend = StatesBackend(_data())
    _ = _run(backend, "O", "enter")
    assert backend.actions == [ReopenState(name=LAST)]


def test_up_and_down_choose_the_state_to_reopen() -> None:
    backend = StatesBackend(_data())
    _ = _run(backend, "O", "down", "down", "down", "up", "enter")
    assert backend.actions == [ReopenState(name="morning")]


def test_up_stops_at_the_first_state() -> None:
    backend = StatesBackend(_data())
    _ = _run(backend, "O", "up", "enter")
    assert backend.actions == [ReopenState(name=LAST)]


def test_escape_closes_the_panel() -> None:
    backend = StatesBackend(_data())
    assert _run(backend, "O", "escape") == (FOOTER, None)
    assert backend.actions == []


def test_any_other_key_closes_the_panel_and_does_nothing_else() -> None:
    backend = StatesBackend(_data())
    assert _run(backend, "O", "down", "x") == (FOOTER, None)  # not the stop question
    assert backend.actions == []


def test_without_state_the_panel_says_so_and_enter_does_nothing() -> None:
    backend = StatesBackend(_data(()))
    _, panel = _run(backend, "O", "enter")
    assert panel == ["no saved state"]
    assert backend.actions == []


def test_the_reopening_shows_in_the_footer_then_its_report() -> None:
    backend = StatesBackend(_data())
    backend.release.clear()
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    seen: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("O", "down", "enter")
            await until(pilot, lambda: backend.actions, "never reopened")
            seen.append(_text(app, "footer"))
            backend.release.set()
            await until(pilot, lambda: _text(app, "footer") == _REPORT, "no report")

    asyncio.run(scenario())
    assert seen == ["reopening morning…"]


def test_a_second_enter_while_reopening_is_ignored() -> None:
    backend = StatesBackend(_data())
    backend.release.clear()
    app = BoardApp(backend, poll_seconds=_NO_POLL)

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("O", "enter")
            await until(pilot, lambda: backend.actions, "never reopened")
            await pilot.press("enter")
            await pilot.pause()
            backend.release.set()
            await until(pilot, lambda: _text(app, "footer") == _REPORT, "no report")

    asyncio.run(scenario())
    assert backend.actions == [ReopenState(name=LAST)]


def test_a_reread_keeps_the_selected_name() -> None:
    backend = StatesBackend(_data())
    app = BoardApp(backend, poll_seconds=0.05)
    newer = (_STATES[0], _state("noon", 1, 60), *_STATES[1:])

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("O", "down")
            backend.pending = _data(newer)
            await until(pilot, lambda: "noon" in _text(app, "saved-states"), "never reread")
            await pilot.press("enter")
            await until(pilot, lambda: _text(app, "footer") == _REPORT, "no report")

    asyncio.run(scenario())
    assert backend.actions == [ReopenState(name="morning")]


def test_o_and_s_do_nothing_while_a_stop_is_asked() -> None:
    for key in ("O", "S"):
        backend = StatesBackend(_data())
        app = BoardApp(backend, poll_seconds=_NO_POLL)

        async def scenario(app: BoardApp = app, key: str = key) -> None:
            async with app.run_test(size=_SIZE) as pilot:
                await pilot.press("x")
                assert _text(app, "footer").startswith("Stop ")
                await pilot.press(key)
                assert _panel(app) is None
                assert _text(app, "footer") == FOOTER  # the key only answered the question

        asyncio.run(scenario())
        assert backend.actions == []


def test_s_and_o_belong_to_the_sessions_tab() -> None:
    backend = StatesBackend(_data())
    _, panel = _run(backend, "tab", "S", "O")
    assert panel is None
    assert not any(isinstance(action, (SaveState, StopSession)) for action in backend.actions)


def test_the_keys_help_tells_what_s_and_o_do() -> None:
    lines = KEYS_HELP.splitlines()
    assert lines[lines.index("W remove the worktree of an ended session") + 1] == (
        "S save the open sessions · O reopen a saved state"
    )
    assert all(len(line) <= 58 for line in lines)


def test_the_footer_texts_show_a_name_literally() -> None:
    name = "a\x1b[31mb"
    assert "\x1b" not in saved_text(name)
    assert "\x1b" not in reopening_text(name)
    assert saved_text("x") == "state saved: x"
    assert reopening_text("x") == "reopening x…"


async def _open_on_morning(pilot: Pilot[None]) -> None:
    await pilot.press("O", "down")


def test_saved_states_60_columns(snap_compare: SnapCompare) -> None:
    app = BoardApp(StatesBackend(_data()), poll_seconds=_NO_POLL)
    assert snap_compare(app, terminal_size=(60, 30), run_before=_open_on_morning)


def test_saved_states_44_columns(snap_compare: SnapCompare) -> None:
    long = (*_STATES, _state("before the long weekend with every repository open", 12, 9000))
    app = BoardApp(StatesBackend(_data(long)), poll_seconds=_NO_POLL)
    assert snap_compare(app, terminal_size=(44, 30), run_before=_open_on_morning)
