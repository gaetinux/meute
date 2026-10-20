"""Editing tasks from the Tasks tab: adding, cancelling, conflicts, deleting and clicks."""

from dataclasses import replace

from textual.pilot import Pilot

from meute.core.board_view import (
    AddNote,
    ChangeTask,
    CreateTask,
    DeleteTask,
)
from meute.core.errors import NotFound
from meute.core.status import Priority
from meute.core.task import TaskId, TaskPatch
from meute.tui.board import BoardApp
from test_tui_task_edit import (  # the helpers of the edit tests
    _MARK,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _ME,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _VERSION,  # pyright: ignore[reportPrivateUsage] — edit test helper
    EditBackend,
    _change,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _data,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _is_open,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _line,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _review,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _run,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _text,  # pyright: ignore[reportPrivateUsage] — edit test helper
    _type,  # pyright: ignore[reportPrivateUsage] — edit test helper
)


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


def test_a_click_on_the_board_keeps_the_line_usable() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("o", "a", "b")
        await pilot.click("#board", offset=(3, 3))
        await pilot.press("c", "d", "enter")
        assert not _is_open(app)

    assert _run(steps).actions == [AddNote(task_id=TaskId(1), body="abcd")]


def test_a_click_on_the_board_keeps_the_list_usable() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("p")
        await pilot.click("#board", offset=(3, 3))
        await pilot.press("down", "enter")
        assert not _is_open(app)

    assert _run(steps).actions == [_change(priority=Priority.HIGH)]


def test_a_task_deleted_meanwhile_closes_the_line_with_the_error() -> None:
    backend = EditBackend(_data())
    backend.error = NotFound("task", "1")

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("o", "x", "enter")
        assert not _is_open(app)
        assert _text(app, "footer") == "Error: task not found: 1"

    assert len(_run(steps, backend).actions) == 1


def test_a_task_deleted_meanwhile_fails_the_delete_once() -> None:
    backend = EditBackend(_data())
    backend.error = NotFound("task", "1")

    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("delete", "y")
        assert _text(app, "footer") == "Error: task not found: 1"
        assert not _is_open(app)

    assert len(_run(steps, backend).actions) == 1


def test_an_unknown_project_suggests_the_closest_one() -> None:
    async def steps(pilot: Pilot[None], app: BoardApp) -> None:
        await pilot.press("at")
        _line(app).value = "infar"
        await pilot.press("enter")
        assert _text(app, "footer") == "Error: unknown project: infar (infra?)"
        assert _is_open(app)

    assert _run(steps).actions == []
