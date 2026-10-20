"""The `M-t` quick task window: typing, preview, Enter, errors and Esc, on a fake backend."""

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol

from textual import events
from textual.color import Color
from textual.containers import Vertical
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Input, Static

from meute.core.errors import MeuteError
from meute.core.project import ProjectId, ProjectRef
from meute.core.task import Task
from meute.tui.quick_task import QuickContext, QuickTaskApp
from support import NOW, make_task

_SIZE = (76, 12)
_ME = ProjectRef(id=ProjectId(1), name="meute")
_INFRA = ProjectRef(id=ProjectId(2), name="infra")
_ACCENT = Color.parse("#3b8eea")
_RED = Color.parse("#f16c6c")


class SnapCompare(Protocol):
    """The `snap_compare` fixture of pytest-textual-snapshot, typed for our use."""

    def __call__(
        self,
        app: QuickTaskApp,
        *,
        press: Iterable[str] = (),
        terminal_size: tuple[int, int] = (80, 24),
        run_before: Callable[[Pilot[None]], Awaitable[None] | None] | None = None,
    ) -> bool: ...


class FakeQuickBackend:
    """Records the texts created; raises `error` instead when it is set."""

    def __init__(self, *, default: ProjectRef | None = _ME) -> None:
        self.default = default
        self.created: list[str] = []
        self.error: MeuteError | None = None

    def context(self) -> QuickContext:
        return QuickContext(now=NOW, default=self.default, projects=(_ME, _INFRA))

    def create(self, text: str) -> Task:
        if self.error is not None:
            raise self.error
        self.created.append(text)
        return make_task(1)


def _plain(app: QuickTaskApp, selector: str) -> str:
    content = app.query_one(selector, Static).content
    assert isinstance(content, Content)
    return content.plain


def _border(app: QuickTaskApp) -> Color:
    return app.query_one("#frame", Vertical).styles.border_top[1]


async def _type(pilot: Pilot[None], text: str) -> None:
    await pilot.press(*text)
    await pilot.pause()


def _run(app: QuickTaskApp, scenario: Callable[[Pilot[None]], Awaitable[None]]) -> None:
    async def main() -> None:
        async with app.run_test(size=_SIZE) as pilot:
            await pilot.pause()
            await scenario(pilot)

    asyncio.run(main())


def test_header_names_the_default_project_and_typing_updates_the_preview() -> None:
    app = QuickTaskApp(FakeQuickBackend())

    async def scenario(pilot: Pilot[None]) -> None:
        assert _plain(app, "#header-title") == "New task"
        assert _plain(app, "#header-project") == "in meute"
        await _type(pilot, "Review the PR !!")
        preview = _plain(app, "#input-preview")
        assert "Title     Review the PR" in preview
        assert "Priority  urgent" in preview
        assert preview.endswith("Enter create · Esc cancel")
        assert _border(app) == _ACCENT

    _run(app, scenario)


def test_enter_creates_and_exits_with_code_0() -> None:
    backend = FakeQuickBackend()
    app = QuickTaskApp(backend)

    async def scenario(pilot: Pilot[None]) -> None:
        await _type(pilot, "Review @infra")
        await pilot.press("enter")
        await pilot.pause()

    _run(app, scenario)
    assert backend.created == ["Review @infra"]
    assert app.return_code == 0


def test_enter_on_an_unknown_project_creates_nothing_and_turns_the_border_red() -> None:
    backend = FakeQuickBackend()
    app = QuickTaskApp(backend)

    async def scenario(pilot: Pilot[None]) -> None:
        await _type(pilot, "Call @infar")
        assert _border(app) == _RED
        await pilot.press("enter")
        await pilot.pause()
        assert app.return_code is None  # still open
        assert app.query_one(Input).value == "Call @infar"
        assert "Error: unknown project" in _plain(app, "#input-preview")

    _run(app, scenario)
    assert backend.created == []


def test_a_failed_creation_keeps_the_window_open_with_the_text_and_the_message() -> None:
    backend = FakeQuickBackend()
    backend.error = MeuteError("database is locked")
    app = QuickTaskApp(backend)

    async def scenario(pilot: Pilot[None]) -> None:
        await _type(pilot, "Review")
        await pilot.press("enter")
        await pilot.pause()
        assert app.return_code is None
        assert app.query_one(Input).value == "Review"
        assert "Error: database is locked" in _plain(app, "#input-preview")
        assert _border(app) == _RED
        await _type(pilot, "s")  # typing again clears the failure
        assert "Error:" not in _plain(app, "#input-preview")
        assert _border(app) == _ACCENT

    _run(app, scenario)


def test_escape_exits_without_creating() -> None:
    backend = FakeQuickBackend()
    app = QuickTaskApp(backend)

    async def scenario(pilot: Pilot[None]) -> None:
        await _type(pilot, "Review")
        await pilot.press("escape")
        await pilot.pause()

    _run(app, scenario)
    assert backend.created == []
    assert app.return_code == 0


def test_without_a_displayed_session_the_task_floats() -> None:
    app = QuickTaskApp(FakeQuickBackend(default=None))

    async def scenario(pilot: Pilot[None]) -> None:
        del pilot
        assert _plain(app, "#header-project") == "floating"
        assert "Project   floating  (no displayed session)" in _plain(app, "#input-preview")

    _run(app, scenario)


def test_alt_t_inside_the_window_types_nothing() -> None:
    # M-t pressed again while the window is open reaches it, not tmux: it must do nothing.
    app = QuickTaskApp(FakeQuickBackend())

    async def scenario(pilot: Pilot[None]) -> None:
        await _type(pilot, "ab")
        app.post_message(events.Key("alt+t", "t"))  # as a terminal sends it: ESC then t
        await pilot.pause()
        assert app.query_one(Input).value == "ab"
        assert app.return_code is None

    _run(app, scenario)


def test_quick_task_ok(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        QuickTaskApp(FakeQuickBackend()),
        press=list("Review PR #11 !! >tomorrow"),
        terminal_size=_SIZE,
    )


def test_quick_task_unknown_project(snap_compare: SnapCompare) -> None:
    assert snap_compare(
        QuickTaskApp(FakeQuickBackend()),
        press=list("Call support @infar >tonight"),
        terminal_size=_SIZE,
    )
