"""The Sessions and Tasks tabs of the board: the Tab key, a click on a name, the keys of each."""

import asyncio

from textual import events
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_header import Tab, tab_at, tabs_line
from meute.core.board_view import KEYS_HELP
from meute.core.styled import Role
from meute.tui.board import BoardApp
from meute.tui.sessions_pane import ROLE_STYLES
from support import board_data
from test_tui_board import FakeBackend

_SIZE = (60, 30)
_NO_POLL = 3600.0


def _content(app: BoardApp, widget_id: str) -> Content:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content


def _text(app: BoardApp, widget_id: str) -> str:
    return _content(app, widget_id).plain


def _on_tasks(app: BoardApp) -> bool:
    return "No tasks yet." in _text(app, "board")


def test_tab_switches_to_tasks_and_back() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    seen: list[bool] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            seen.append(_on_tasks(app))
            await pilot.press("tab")
            seen.append(_on_tasks(app))
            await pilot.press("tab")
            seen.append(_on_tasks(app))

    asyncio.run(scenario())
    assert seen == [False, True, False]


def test_click_on_the_tasks_name_chooses_the_tab() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    seen: list[bool] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            line = tabs_line(Tab.SESSIONS, overdue=0, totals="", width=_SIZE[0])
            text = "".join(span.text for span in line)
            await pilot.click("#title", offset=(text.index("Tasks") + 1, 0))
            seen.append(_on_tasks(app))
            await pilot.click("#title", offset=(text.index("Sessions") + 1, 0))
            seen.append(_on_tasks(app))
            await pilot.click("#title", offset=(_SIZE[0] - 2, 0))  # the totals: no tab
            seen.append(_on_tasks(app))

    asyncio.run(scenario())
    assert seen == [True, False, False]


def test_tab_at_maps_a_column_to_the_tab_whose_name_holds_it() -> None:
    line = tabs_line(Tab.TASKS, overdue=0, totals="3 open", width=40)
    assert [tab_at(line, x) for x in (0, 1, 9, 10, 11, 16, 17, 39)] == [
        Tab.SESSIONS, Tab.SESSIONS, Tab.SESSIONS, Tab.TASKS, Tab.TASKS, Tab.TASKS, None, None,
    ]  # fmt: skip


def test_sessions_keys_do_nothing_on_tasks() -> None:
    backend = FakeBackend(board_data())
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    footers: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("tab")
            for key in ("x", "c", "n", "a", "e", "enter", "space"):
                await pilot.press(key)
            footers.append(_text(app, "footer"))
            assert _on_tasks(app)

    asyncio.run(scenario())
    assert backend.actions == []
    assert not footers[0].startswith("Stop ")


def test_question_mark_escape_and_q_still_work_on_tasks() -> None:
    backend = FakeBackend(board_data())
    app = BoardApp(backend, poll_seconds=_NO_POLL)
    seen: list[str] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("tab", "question_mark")
            seen.append(_text(app, "footer"))
            await pilot.press("escape")
            seen.append(_text(app, "footer"))
            await pilot.press("q")

    asyncio.run(scenario())
    assert seen[0] != seen[1]
    assert seen[0] != KEYS_HELP
    assert [type(a).__name__ for a in backend.actions] == ["Detach"]


def test_sessions_selection_is_the_same_after_a_round_trip() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    boards: list[Content] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("down")
            boards.append(_content(app, "board"))
            await _round_trip(pilot)
            boards.append(_content(app, "board"))

    asyncio.run(scenario())
    assert boards[0].plain == boards[1].plain
    assert boards[0].spans == boards[1].spans  # the same line stays highlighted


async def _round_trip(pilot: Pilot[None]) -> None:
    await pilot.press("tab", "tab")


def test_tab_while_a_stop_is_pending_only_cancels_it() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    seen: list[bool] = []

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("x", "tab")
            seen.append(_on_tasks(app))

    asyncio.run(scenario())
    assert seen == [False]


def test_the_focus_cue_follows_the_active_tab_on_tasks() -> None:
    app = BoardApp(FakeBackend(board_data()), poll_seconds=_NO_POLL)
    seen: list[list[tuple[str, str]]] = []

    def tab_styles() -> list[tuple[str, str]]:
        title = _content(app, "title")
        return [(title.plain[s.start : s.end].strip(), str(s.style)) for s in title.spans][:2]

    async def scenario() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.press("tab")
            seen.append(tab_styles())
            app.post_message(events.AppBlur())
            await pilot.pause()
            seen.append(tab_styles())

    asyncio.run(scenario())
    assert seen[0] == [("Sessions", ROLE_STYLES[Role.TAB]), ("Tasks", ROLE_STYLES[Role.TAB_ACTIVE])]
    assert seen[1] == [
        ("Sessions", ROLE_STYLES[Role.TAB]),
        ("Tasks", f"{ROLE_STYLES[Role.TAB]} underline"),
    ]
