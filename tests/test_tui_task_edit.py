"""Editing tasks from the Tasks tab: one key per action, a line or a short list at the bottom."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import replace

from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Input, OptionList, Static

from meute.core.board_view import (
    AddNote,
    BoardAction,
    BoardData,
    ChangeTask,
)
from meute.core.errors import MeuteError, VersionConflict
from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, InProgress, Priority
from meute.core.task import Task, TaskId, TaskPatch
from meute.core.task_postpone import Postpone, postpone
from meute.tui.board import BoardApp, BoardOptions
from support import BOARD_HOME, NOW, at_due, make_task

_NO_POLL = 3600.0
_ME = ProjectRef(id=ProjectId(1), name="meute")
_INFRA = ProjectRef(id=ProjectId(2), name="infra")
_VERSION = 3
_MARK = "\u203a "  # the prompt mark, a single right-pointing angle quote


def _review(version: int = _VERSION) -> Task:
    task = make_task(1, due=at_due("2026-10-14T08:30[Europe/Paris]"), priority=Priority.URGENT)
    return replace(
        task, title="Review the PR", description="first\nsecond", project=_ME, version=version
    )


def _data(*tasks: Task) -> BoardData:
    support = replace(make_task(2, due=at_due("2026-10-14T18:00[Europe/Paris]")), title="Call")
    return BoardData(
        sessions=(),
        repos=(),
        orphans=(),
        home=BOARD_HOME,
        now=NOW,
        tasks=tasks or (_review(), support),
        project_refs=(_ME, _INFRA),
        displayed_project=_ME,
    )


class EditBackend:
    """Records the actions; `conflict` makes the next action fail and become the new data."""

    def __init__(self, data: BoardData) -> None:
        self.data = data
        self.pending: BoardData | None = data
        self.actions: list[BoardAction] = []
        self.loads = 0
        self.conflict: Task | None = None
        self.error: MeuteError | None = None  # raised by the next action only

    def load(self) -> BoardData | None:
        self.loads += 1
        data, self.pending = self.pending, None
        return data

    def perform(self, action: BoardAction) -> None:
        self.actions.append(action)
        error, self.error = self.error, None
        if error is not None:
            raise error
        current, self.conflict = self.conflict, None
        if current is not None:
            others = tuple(task for task in self.data.tasks if task.id != current.id)
            self.data = replace(self.data, tasks=(current, *others))
            self.pending = self.data
            raise VersionConflict(current)


Steps = Callable[[Pilot[None], BoardApp], Awaitable[None]]


def _run(steps: Steps, backend: EditBackend | None = None) -> EditBackend:
    backend = backend or EditBackend(_data())
    app = BoardApp(backend, BoardOptions(), poll_seconds=_NO_POLL)

    async def run() -> None:
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press("tab")
            await steps(pilot, app)

    asyncio.run(run())
    return backend


def _text(app: BoardApp, widget_id: str) -> str:
    content = app.query_one(f"#{widget_id}", Static).content
    assert isinstance(content, Content)
    return content.plain


def _line(app: BoardApp) -> Input:
    return app.query_one("#input-line", Input)


def _is_open(app: BoardApp) -> bool:
    return app.query_one("#task-input").display


async def _type(pilot: Pilot[None], text: str) -> None:
    await pilot.press(*("space" if char == " " else char for char in text))


def _change(**patch: object) -> ChangeTask:
    return ChangeTask(task_id=TaskId(1), version=_VERSION, patch=TaskPatch(**patch))  # pyright: ignore[reportArgumentType] — test shorthand


def test_the_input_is_hidden_until_an_edit_key() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = pilot
        assert not _is_open(app)

    assert _run(steps).actions == []


def test_s_picks_a_status_with_the_version_read() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("s")
        assert _is_open(app)
        choices = app.query_one("#input-choices", OptionList)
        labels = [str(choices.get_option_at_index(i).prompt) for i in range(choices.option_count)]
        assert labels == ["todo", "in progress", "blocked", "review", "done"]
        await pilot.press("down", "enter")
        assert not _is_open(app)

    assert _run(steps).actions == [_change(status=InProgress())]


def test_blocked_asks_for_the_reason() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("s", "down", "down", "enter")
        assert _is_open(app)
        assert _text(app, "input-label") == _MARK + "Blocked reason: "
        await pilot.press("enter")  # a blank reason is refused, the line stays
        assert _text(app, "footer") == "Error: a blocked task needs a non-empty reason"
        assert _is_open(app)
        await _type(pilot, "waiting for CI")
        await pilot.press("enter")
        assert not _is_open(app)

    assert _run(steps).actions == [_change(status=Blocked(reason="waiting for CI"))]


def test_p_picks_a_priority() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = app
        await pilot.press("p", "down", "down", "enter")  # from urgent, the current one

    assert _run(steps).actions == [_change(priority=Priority.NORMAL)]


def test_d_postpones_from_the_board_clock() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("d")
        choices = app.query_one("#input-choices", OptionList)
        labels = [str(choices.get_option_at_index(i).prompt) for i in range(choices.option_count)]
        assert labels == ["+1h", "tonight 6pm", "tomorrow 9am", "Monday 9am", "clear"]
        await pilot.press("down", "down", "enter")

    assert _run(steps).actions == [_change(due=postpone(Postpone.TOMORROW, NOW))]


def test_d_clear_removes_the_due() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        _ = app
        await pilot.press("d", "down", "down", "down", "down", "enter")

    assert _run(steps).actions == [_change(due=None)]


def test_e_edits_the_prefilled_title() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("e")
        assert _text(app, "input-label") == _MARK + "Title: "
        assert _line(app).value == "Review the PR"
        await _type(pilot, " now")
        await pilot.press("enter")

    assert _run(steps).actions == [_change(title="Review the PR now")]


def test_shift_d_edits_a_one_line_description() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("D")
        assert _text(app, "input-label") == _MARK + "Description: "
        assert _line(app).value == "only line"
        await _type(pilot, "!")
        await pilot.press("enter")

    backend = EditBackend(_data(replace(_review(), description="only line")))
    assert _run(steps, backend).actions == [_change(description="only line!")]


def test_shift_d_leaves_a_multi_line_description_alone() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("D")
        assert not _is_open(app)
        assert _text(app, "footer") == "multi-line description: edit it with meute task edit"

    assert _run(steps).actions == []


def test_the_footer_shows_the_edit_keys_while_editing() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("e")
        assert _text(app, "footer") == "Enter confirm · Esc cancel"
        await pilot.press("escape", "p")
        assert _text(app, "footer") == "Enter confirm · Esc cancel"
        await pilot.press("escape")
        assert _text(app, "footer") == "a add · s status · d postpone · o note · L Claude · ? keys"

    assert _run(steps).actions == []


def test_at_moves_the_task_to_a_project_or_floats_it() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("at")
        assert _text(app, "input-label") == _MARK + "Project (none: floating): "
        assert _line(app).value == "meute"
        _line(app).value = "INFRA"
        await pilot.press("enter")
        await pilot.press("at")
        _line(app).value = "none"
        await pilot.press("enter")
        await pilot.press("at")
        _line(app).value = " "
        await pilot.press("enter")

    assert _run(steps).actions == [
        _change(project_id=ProjectId(2)),
        _change(project_id=None),
        _change(project_id=None),
    ]


def test_an_unknown_project_is_an_error_and_keeps_the_line() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("at")
        _line(app).value = "nope"
        await pilot.press("enter")
        assert _text(app, "footer") == "Error: unknown project: nope"
        assert _is_open(app)
        assert _line(app).value == "nope"

    assert _run(steps).actions == []


def test_o_adds_a_note() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("o")
        assert _text(app, "input-label") == _MARK + "Note: "
        assert _line(app).value == ""
        await _type(pilot, "asked Bob")
        await pilot.press("enter")

    assert _run(steps).actions == [AddNote(task_id=TaskId(1), body="asked Bob")]
