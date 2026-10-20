"""The Tasks tab of the dashboard: navigation, filters, groups, folds, detail, Enter, footer."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    FOOTER,
    TASKS_FOOTER,
    TASKS_KEYS_HELP,
    BoardData,
    SessionRow,
    ShowSession,
)
from meute.core.project import ProjectId, ProjectRef
from meute.core.session import SessionId
from meute.core.session_state import Exited, Running
from meute.core.status import Priority
from meute.core.task import Task, TaskId
from meute.tui.board import BoardApp, BoardOptions
from meute.tui.sessions_pane import SELECTED_STYLE
from support import (
    BOARD_HOME,
    BOARD_ID_A,
    BOARD_ID_B,
    NOW,
    at_due,
    board_session,
    make_task,
    selected_row,
)
from test_tui_board import FakeBackend, SnapCompare

_NO_POLL = 3600.0
_ME = ProjectRef(id=ProjectId(1), name="meute")


def _tasks() -> tuple[Task, ...]:
    late = replace(
        make_task(1, due=at_due("2026-10-14T08:30[Europe/Paris]"), priority=Priority.URGENT),
        title="Review the PR",
        project=_ME,
    )
    soon = replace(make_task(2, due=at_due("2026-10-14T18:00[Europe/Paris]")), title="Call support")
    later = replace(make_task(3, due=at_due("2026-10-16T09:00[Europe/Paris]")), title="Demo")
    return (late, soon, later)


def _data(tasks: tuple[Task, ...] | None = None, **extra: object) -> BoardData:
    return replace(
        BoardData(sessions=(), repos=(), orphans=(), home=BOARD_HOME, now=NOW),
        tasks=_tasks() if tasks is None else tasks,
        displayed_project=_ME,
        **extra,
    )


def _app(data: BoardData) -> tuple[BoardApp, FakeBackend]:
    backend = FakeBackend(data)
    return BoardApp(backend, BoardOptions(), poll_seconds=_NO_POLL), backend


def _run(
    data: BoardData,
    steps: Callable[[Pilot[None], BoardApp], Awaitable[None]],
    size: tuple[int, int] = (80, 30),
) -> FakeBackend:
    app, backend = _app(data)

    async def run() -> None:
        async with app.run_test(size=size) as pilot:
            await pilot.press("tab")
            await steps(pilot, app)

    asyncio.run(run())
    return backend


def _text(app: BoardApp, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content.plain


def _selected(app: BoardApp) -> list[str]:
    content = app.query_one("#board", Static).content
    assert isinstance(content, Content)
    return selected_row(content, (SELECTED_STYLE,))


def test_tab_shows_the_tasks_with_filters_detail_and_footer() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = pilot
        assert "Overdue (1)" in _text(app, "board")
        assert "all " in _text(app, "quota")
        assert "─ #1 Review the PR" in _text(app, "details")
        assert _text(app, "footer") == TASKS_FOOTER
        assert _text(app, "title").startswith(" Sessions  Tasks  1!")

    _ = _run(_data(), steps)


def test_arrows_and_jk_move_the_selection() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        assert "Review the PR" in _selected(app)[0]
        await pilot.press("down")
        assert "Call support" in _selected(app)[0]
        assert "─ #2 Call support" in _text(app, "details")
        await pilot.press("j", "k", "k", "k")
        assert "Review the PR" in _selected(app)[0]

    _ = _run(_data(), steps)


def test_f_cycles_the_filter() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("f")
        board = _text(app, "board")
        assert "Review the PR" in board
        assert "Call support" not in board
        await pilot.press("f")
        board = _text(app, "board")
        assert "Call support" in board
        assert "Review the PR" not in board
        await pilot.press("f")
        assert "Review the PR" in _text(app, "board")
        assert "Call support" in _text(app, "board")

    _ = _run(_data(), steps)


def test_g_groups_by_project() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("g")
        board = _text(app, "board")
        assert "meute (1)" in board
        assert "Floating (2)" in board
        await pilot.press("g")
        assert "Overdue (1)" in _text(app, "board")

    _ = _run(_data(), steps)


def test_space_folds_and_enter_unfolds() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("space")
        board = _text(app, "board")
        assert "▶ Overdue (1)" in board
        assert "Review the PR" not in board
        assert _selected(app) == ["▶ Overdue (1)".ljust(80)]
        await pilot.press("enter")
        assert "▼ Overdue (1)" in _text(app, "board")
        assert "Review the PR" in _selected(app)[0]
        await pilot.press("left")
        assert "▶ Overdue (1)" in _text(app, "board")
        await pilot.press("right")
        assert "▼ Overdue (1)" in _text(app, "board")

    _ = _run(_data(), steps)


def test_enter_shows_the_most_recent_live_linked_session() -> None:
    def linked(session_id: SessionId, title: str, minutes: int, *, live: bool) -> SessionRow:
        session = board_session(session_id, title, BOARD_HOME, None, exited=not live)
        session = replace(
            session,
            task_id=TaskId(1),
            state=Running() if live else Exited(code=0),
            last_activity_at=NOW - timedelta(minutes=minutes),
        )
        return SessionRow(session=session, has_pane=True, displayed=False)

    older = linked(BOARD_ID_A, "older", 30, live=True)
    newer = linked(BOARD_ID_B, "newer", 5, live=True)
    gone = linked(SessionId("33333333-3333-4333-8333-333333333333"), "gone", 1, live=False)

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = app
        await pilot.press("enter")

    backend = _run(_data(sessions=(older, newer), ended=(gone,)), steps)
    assert backend.actions == [ShowSession(session_id=BOARD_ID_B)]


def test_enter_without_a_live_session_does_nothing() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = app
        await pilot.press("enter")

    assert _run(_data(), steps).actions == []


def test_help_follows_the_current_tab() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("question_mark")
        assert _text(app, "footer") == TASKS_KEYS_HELP
        await pilot.press("tab")
        assert _text(app, "footer") != TASKS_KEYS_HELP
        assert "Tab tasks" in _text(app, "footer")

    _ = _run(_data(), steps)


def test_overdue_count_shows_from_the_sessions_tab() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("tab")
        assert _text(app, "footer") == FOOTER
        assert _text(app, "title").startswith(" Sessions  Tasks  1!")

    _ = _run(_data(), steps)


def test_click_selects_a_task_and_folds_a_heading() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.click("#board", offset=(3, 3))
        assert "Call support" in _selected(app)[0]
        await pilot.click("#board", offset=(3, 0))
        assert "▶ Overdue (1)" in _text(app, "board")

    _ = _run(_data(), steps)


def test_500_tasks_rebuild_and_draw_in_under_100_ms() -> None:
    many = tuple(
        replace(make_task(n, due=at_due("2026-10-14T18:00[Europe/Paris]")), title=f"task {n}")
        for n in range(1, 501)
    )
    backend = FakeBackend(_data())
    app = BoardApp(backend, BoardOptions(), poll_seconds=0.01)

    async def run() -> None:
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press("tab")
            backend.pending = _data(many)
            start = time.perf_counter()  # from the new data to the redrawn list: poll included
            while "task 500" not in _text(app, "board"):  # noqa: ASYNC110 — the app has no event to wait on
                await asyncio.sleep(0.001)
            assert time.perf_counter() - start < 0.1

    asyncio.run(run())


def _snap(data: BoardData) -> BoardApp:
    return _app(data)[0]


def test_tasks_tab_60_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_snap(_data()), press=["tab"], terminal_size=(60, 30))


def test_tasks_tab_100_columns(snap_compare: SnapCompare) -> None:
    assert snap_compare(_snap(_data()), press=["tab", "down"], terminal_size=(100, 30))


def test_tasks_tab_empty(snap_compare: SnapCompare) -> None:
    assert snap_compare(_snap(_data(())), press=["tab"], terminal_size=(60, 30))


def test_tasks_footer_fits_one_line_at_60_columns() -> None:
    assert TASKS_FOOTER == "a add · s status · d postpone · o note · L Claude · ? keys"
    assert len(TASKS_FOOTER) <= 58
