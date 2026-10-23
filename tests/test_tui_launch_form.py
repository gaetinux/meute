"""`N` opens the launch form: its keys, its launches and their errors, its renderings."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from textual import events
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Static

from meute.core.board_view import (
    KEYS_HELP,
    BoardData,
    LaunchBash,
    LaunchClaude,
    SessionRow,
)
from meute.core.config_validate import PERMISSION_MODES
from meute.core.errors import MeuteError
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.task import DueDate, TaskId
from meute.tui.board import BoardApp, BoardOptions
from support import (
    BOARD_AT,
    BOARD_HOME,
    BOARD_SESSION_A,
    board_data,
    make_task,
)
from test_tui_board import FakeBackend, SnapCompare

_NO_POLL = 3600.0
_SIZE = (72, 30)
_PROJECT = ProjectRef(id=ProjectId(7), name="meute")
_OTHER_MODE = min(PERMISSION_MODES - {"auto"})
_MEUTE = BOARD_HOME / "git" / "meute"
_SEMICOLON = "/srv/x;"
_WARNING_AT_72 = "⚠ another live session works in this folder: a new worktree is recommen…"

Scenario = Callable[[BoardApp, Pilot[None]], Awaitable[None]]


def _data() -> BoardData:
    """Two repositories, no session: the selection starts on the repository `meute`."""
    due = DueDate(day=(BOARD_AT + timedelta(days=1)).date())
    tasks = (
        replace(make_task(1, due=due), project=_PROJECT),
        replace(make_task(2, due=DueDate(day=BOARD_AT.date())), project=_PROJECT),
    )
    return replace(
        board_data(),
        sessions=(),
        orphans=(),
        tasks=tasks,
        repo_projects={RepoId(1): _PROJECT.id},
    )


def _app(backend: FakeBackend, poll: float = _NO_POLL) -> BoardApp:
    return BoardApp(backend, BoardOptions(permission_mode="auto"), poll_seconds=poll)


def _text(app: BoardApp, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content.plain


def _is_open(app: BoardApp) -> bool:
    return app.query_one("#launch-form", Static).display


def _run(backend: FakeBackend, scenario: Scenario, size: tuple[int, int] = _SIZE) -> None:
    app = _app(backend)

    async def run() -> None:
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(run())


def _backend() -> FakeBackend:
    return FakeBackend(_data())


async def _type(pilot: Pilot[None], text: str) -> None:
    await pilot.press(*text)


async def _clear_folder(pilot: Pilot[None]) -> None:
    await pilot.press(*["backspace"] * len(str(_MEUTE)))


def test_n_opens_the_form_prefilled_on_the_selected_repository() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        assert not _is_open(app)
        await pilot.press("N")
        assert _is_open(app)
        shown = _text(app, "launch-form")
        for expected in ("── New session", "Claude", "meute", "~/git/meute", "Mode", "auto"):
            assert expected in shown
        assert "Task      ◂ none ▸" in shown

    _run(_backend(), scenario)


def test_choosing_bash_hides_task_and_mode() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "right")
        shown = _text(app, "launch-form")
        assert "Bash" in shown
        assert "Task" not in shown
        assert "Mode" not in shown

    _run(_backend(), scenario)


def test_a_bash_launch_with_a_title() -> None:
    backend = _backend()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "right", "down", "down", "down", "down")
        await _type(pilot, "hi there")
        await pilot.press("enter")
        assert not _is_open(app)

    _run(backend, scenario)
    assert backend.actions == [LaunchBash(cwd=_MEUTE, repo_id=RepoId(1), title="hi there")]


def test_a_claude_launch_with_a_task_and_a_mode() -> None:
    backend = _backend()

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "tab", "tab", "tab", "tab", "tab", "right")  # the Task field
        await pilot.press("tab", "right", "enter")  # the Mode field

    _run(backend, scenario)
    assert backend.actions == [
        LaunchClaude(
            cwd=_MEUTE,
            repo_id=RepoId(1),
            title=None,
            task_id=TaskId(2),
            permission_mode=_OTHER_MODE,
        )
    ]


def test_a_relative_folder_is_an_error_and_nothing_is_sent() -> None:
    backend = _backend()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "down", "down", "down")
        await _clear_folder(pilot)
        await _type(pilot, "relative")
        await pilot.press("enter")
        assert _is_open(app)
        assert "Error: folder must be absolute: relative" in _text(app, "launch-form")

    _run(backend, scenario)
    assert backend.actions == []


def test_a_folder_ending_with_a_semicolon_is_sent_as_typed() -> None:
    backend = _backend()

    async def scenario(_app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "down", "down", "down")
        await _clear_folder(pilot)
        await _type(pilot, _SEMICOLON)
        await pilot.press("enter")

    _run(backend, scenario)
    [action] = backend.actions
    assert isinstance(action, LaunchClaude)
    assert action.cwd == Path(_SEMICOLON)


def test_a_failed_launch_keeps_the_form_its_text_and_the_error() -> None:
    backend = _backend()
    backend.perform_error = MeuteError("folder not found: /x")

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "down", "down", "down", "down")
        await _type(pilot, "my title")
        await pilot.press("enter")
        shown = _text(app, "launch-form")
        assert _is_open(app)
        assert "Error: folder not found: /x" in shown
        assert "my title" in shown
        backend.perform_error = None
        await pilot.press("enter")  # the same form, launched again
        assert not _is_open(app)

    _run(backend, scenario)
    assert len(backend.actions) == 2
    assert backend.actions[0] == backend.actions[1]


def test_escape_closes_the_form() -> None:
    backend = _backend()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "escape")
        assert not _is_open(app)
        await pilot.press("N", "escape")
        assert not _is_open(app)

    _run(backend, scenario)
    assert backend.actions == []


def test_the_form_takes_every_key() -> None:
    backend = _backend()

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        board = _text(app, "board")
        footer = _text(app, "footer")
        await pilot.press("N", "down", "down", "down", "down")  # the Title field
        await pilot.press("x", "q", "y", "c", "n", "a", "e", "question_mark", "space")
        assert _text(app, "launch-form").splitlines()[5] == "Title     xqycnae? "
        await pilot.press("tab", "tab", "shift+tab", "up", "left", "right", "backspace")
        assert _is_open(app)
        assert _text(app, "board") == board
        assert _text(app, "footer") == footer

    _run(backend, scenario)
    assert backend.actions == []


def test_a_click_elsewhere_keeps_the_form_and_its_keys() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N")
        await pilot.click("#title", offset=(20, 0))  # on the name of the Tasks tab
        await pilot.click("#board", offset=(3, 1))
        assert _is_open(app)
        await pilot.press("right")
        assert "Bash" in _text(app, "launch-form")

    _run(_backend(), scenario)


def test_a_paste_is_added_to_the_current_text_field() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "down", "down", "down", "down")
        app.post_message(events.Paste("one\ntwo\x1b[2J"))
        await pilot.pause()
        assert "one two" in _text(app, "launch-form")
        assert "\x1b" not in _text(app, "launch-form")

    _run(_backend(), scenario)


def test_a_paste_without_the_form_does_nothing() -> None:
    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        app.post_message(events.Paste("hello"))
        await pilot.pause()
        assert not _is_open(app)

    _run(_backend(), scenario)


def test_a_reread_while_the_form_is_open_changes_only_the_busy_folders() -> None:
    backend = _backend()
    session = replace(BOARD_SESSION_A, cwd=_MEUTE)
    busy = replace(_data(), sessions=(SessionRow(session=session, has_pane=True, displayed=False),))

    async def scenario(app: BoardApp, pilot: Pilot[None]) -> None:
        await pilot.press("N", "tab", "tab", "tab", "tab")  # the Title field
        await _type(pilot, "abc")
        before = _text(app, "launch-form")
        assert "another live session" not in before
        deadline = time.monotonic() + 10
        backend.pending = busy
        while backend.pending is busy:
            assert time.monotonic() < deadline, "the board never reloaded"
            await pilot.pause(0.01)
        await pilot.pause()
        after = _text(app, "launch-form")
        assert after.replace(f"{_WARNING_AT_72}\n", "") == before
        assert "⚠ another live session works in this folder" in after
        await pilot.press("d")
        assert _text(app, "launch-form").splitlines()[5] == "Title     abcd"

    app = _app(backend, 0.01)

    async def run() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            await scenario(app, pilot)

    asyncio.run(run())


def test_the_keys_help_tells_what_capital_n_does() -> None:
    assert "N choose what to launch" in KEYS_HELP
    assert all(len(line) <= 58 for line in KEYS_HELP.splitlines())


def _snapshot(snap_compare: SnapCompare, width: int, *keys: str) -> bool:
    return snap_compare(_app(_backend()), press=["N", *keys], terminal_size=(width, 30))


def test_form_60_columns(snap_compare: SnapCompare) -> None:
    assert _snapshot(snap_compare, 60)


def test_form_72_columns(snap_compare: SnapCompare) -> None:
    assert _snapshot(snap_compare, 72, "right", "tab", "tab", "tab", "tab", "a", "b")


def test_form_100_columns(snap_compare: SnapCompare) -> None:
    assert _snapshot(snap_compare, 100, "tab", "tab", "tab", "tab", "tab", "tab")
