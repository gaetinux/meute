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
    CreateTask,
    DeleteTask,
)
from meute.core.errors import VersionConflict
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

    def load(self) -> BoardData | None:
        self.loads += 1
        data, self.pending = self.pending, None
        return data

    def perform(self, action: BoardAction) -> None:
        self.actions.append(action)
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


def test_a_adds_a_task_with_a_live_preview() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("a")
        assert _text(app, "input-label") == _MARK + "New task: "
        assert "meute  (displayed session · @none: floating)" in _text(app, "input-preview")
        await _type(pilot, "Buy milk @infra")
        preview = _text(app, "input-preview")
        assert "Buy milk" in preview
        assert "infra" in preview
        await pilot.press("enter")
        assert not _is_open(app)

    assert _run(steps).actions == [CreateTask(text="Buy milk @infra", project=_ME)]


def test_a_does_not_create_what_the_preview_refuses() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("a")
        await _type(pilot, "Buy @nope")
        assert "Cannot create: fix the project" in _text(app, "input-preview")
        await pilot.press("enter")
        assert _is_open(app)

    assert _run(steps).actions == []


def test_a_works_without_any_task() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("s")  # needs a task: nothing opens
        assert not _is_open(app)
        await pilot.press("a")
        await _type(pilot, "First")
        await pilot.press("enter")

    backend = EditBackend(replace(_data(), tasks=()))
    assert _run(steps, backend).actions == [CreateTask(text="First", project=_ME)]


def test_escape_closes_and_sends_nothing() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("e")
        await _type(pilot, "x")
        await pilot.press("escape")
        assert not _is_open(app)
        await pilot.press("s", "escape")
        assert not _is_open(app)
        await pilot.press("tab")  # the board's keys work again
        assert _text(app, "title").startswith(" Sessions")

    assert _run(steps).actions == []


def test_typed_keys_never_reach_the_board() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("o")
        await pilot.press("q", "x", "tab", "question_mark", "f", "g", "a", "s", "k", "j")
        assert _is_open(app)
        assert _line(app).value == "qx?fgaskj"
        assert "Overdue" in _text(app, "board")  # still the Tasks tab, same grouping
        assert "all " in _text(app, "quota")
        await pilot.press("escape")
        await pilot.press("p", "q", "x", "tab")  # the choice list swallows them too
        assert _is_open(app)

    assert _run(steps).actions == []


def test_a_version_conflict_reloads_and_keeps_the_typed_text() -> None:
    backend = EditBackend(_data())
    backend.conflict = replace(_review(version=_VERSION + 1), title="Review the PR again")

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("e")
        _line(app).value = "Review it"
        loads = backend.loads
        await pilot.press("enter")
        assert _text(app, "footer") == "#1 was modified in the meantime: reloaded"
        assert backend.loads > loads
        assert "Review the PR again" in _text(app, "board")
        assert _is_open(app)
        assert _line(app).value == "Review it"
        await pilot.press("enter")
        assert not _is_open(app)

    actions = _run(steps, backend).actions
    patch = TaskPatch(title="Review it")
    assert actions == [
        ChangeTask(task_id=TaskId(1), version=_VERSION, patch=patch),
        ChangeTask(task_id=TaskId(1), version=_VERSION + 1, patch=patch),
    ]


def test_a_version_conflict_keeps_the_choice_list_open() -> None:
    backend = EditBackend(_data())
    backend.conflict = _review(version=_VERSION + 1)

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("p", "down", "enter")
        assert _text(app, "footer") == "#1 was modified in the meantime: reloaded"
        assert _is_open(app)
        await pilot.press("enter")
        assert not _is_open(app)

    actions = _run(steps, backend).actions
    assert [action.version for action in actions if isinstance(action, ChangeTask)] == [
        _VERSION,
        _VERSION + 1,
    ]


def test_delete_asks_first_and_any_other_key_cancels() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("delete")
        assert _text(app, "footer") == 'Delete #1 "Review the PR"? y: yes · any other key: no'
        await pilot.press("n")
        assert "Delete" not in _text(app, "footer")
        await pilot.press("delete")
        await pilot.click("#board", offset=(3, 3))  # a click only cancels too
        assert "Delete" not in _text(app, "footer")
        await pilot.press("delete", "y")

    assert _run(steps).actions == [DeleteTask(task_id=TaskId(1), version=_VERSION)]


def test_delete_prompt_neutralises_the_title() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("delete")
        assert _text(app, "footer") == 'Delete #1 "a�[2Jb"? y: yes · any other key: no'

    backend = EditBackend(_data(replace(_review(), title="a\x1b[2Jb")))
    _ = _run(steps, backend)
