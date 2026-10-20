"""The task edits of the Tasks tab: what each key asks for on the line, what Enter sends."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, tzinfo
from enum import Enum
from typing import assert_never

from meute.core.board_view import (
    MULTILINE_DESCRIPTION,
    AddNote,
    BoardData,
    ChangeTask,
    CreateTask,
    TaskAction,
    conflict_text,
)
from meute.core.errors import MeuteError, NotFound, VersionConflict
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_preview import (
    QuickPreview,
    choice_project_id,
    preview_lines,
    quick_preview,
    resolve_quick_project,
)
from meute.core.status import Priority, StatusKind, status_from_kind, status_kind
from meute.core.task import Task, TaskPatch
from meute.core.task_postpone import Postpone, postpone
from meute.core.text import printable
from meute.tui.task_input import Ask, ChoiceAsk, TaskInput, TextAsk
from meute.tui.tasks_pane import rows_content


class _TextField(Enum):
    """A field edited on the line; the value is its label."""

    BLOCKED = "Blocked reason: "
    TITLE = "Title: "
    DESCRIPTION = "Description: "
    PROJECT = "Project (none: floating): "
    NOTE = "Note: "


class _ChoiceField(Enum):
    """A field picked from the list."""

    STATUS = "status"
    PRIORITY = "priority"
    POSTPONE = "postpone"


NEW_TASK_LABEL = "New task: "
_TEXT_KEYS = {
    "e": _TextField.TITLE,
    "D": _TextField.DESCRIPTION,
    "at": _TextField.PROJECT,
    "o": _TextField.NOTE,
}
_CHOICE_KEYS = {"s": _ChoiceField.STATUS, "p": _ChoiceField.PRIORITY, "d": _ChoiceField.POSTPONE}
_STATUSES = (
    (StatusKind.TODO, "todo"),
    (StatusKind.IN_PROGRESS, "in progress"),
    (StatusKind.BLOCKED, "blocked"),
    (StatusKind.REVIEW, "review"),
    (StatusKind.DONE, "done"),
)
_PRIORITIES = tuple(Priority)
_POSTPONES = tuple(Postpone)


@dataclass(frozen=True, slots=True)
class _TaskEdit:
    """A change to `task`, at the version it had when read."""

    field: _TextField | _ChoiceField
    task: Task


@dataclass(frozen=True, slots=True)
class _NewTask:
    """A quick entry for a new task."""


def _text_ask(field: _TextField, task: Task) -> TextAsk:
    match field:
        case _TextField.TITLE:
            value = task.title
        case _TextField.DESCRIPTION:
            value = "".join(task.description.splitlines())  # one line at most here
        case _TextField.PROJECT:
            value = "" if task.project is None else task.project.name
        case _TextField.BLOCKED | _TextField.NOTE:
            value = ""
        case _:
            assert_never(field)
    return TextAsk(label=field.value, value=printable(value))


def _choice_ask(field: _ChoiceField, task: Task) -> ChoiceAsk:
    match field:
        case _ChoiceField.STATUS:
            kinds = [kind for kind, _ in _STATUSES]
            labels = tuple(label for _, label in _STATUSES)
            return ChoiceAsk(choices=labels, highlighted=kinds.index(status_kind(task.status)))
        case _ChoiceField.PRIORITY:
            labels = tuple(priority.value for priority in _PRIORITIES)
            return ChoiceAsk(choices=labels, highlighted=_PRIORITIES.index(task.priority))
        case _ChoiceField.POSTPONE:
            return ChoiceAsk(choices=tuple(choice.value for choice in _POSTPONES))
        case _:
            assert_never(field)


def _ask(edit: _TaskEdit | _NewTask) -> Ask:
    if isinstance(edit, _NewTask):
        return TextAsk(label=NEW_TASK_LABEL)
    if isinstance(edit.field, _TextField):
        return _text_ask(edit.field, edit.task)
    return _choice_ask(edit.field, edit.task)


def _project_id(text: str, projects: Sequence[ProjectRef]) -> ProjectId | None:
    """The project typed on the line: blank or `none` floats; raises `InvalidInput` if unknown."""
    if not text.strip():
        return None
    return choice_project_id(resolve_quick_project(text, None, projects))


def _text_action(field: _TextField, task: Task, text: str, data: BoardData) -> TaskAction:
    """What the line asks for; raises `InvalidInput` for a blank reason or an unknown project."""
    match field:
        case _TextField.BLOCKED:
            patch = TaskPatch(status=status_from_kind(StatusKind.BLOCKED, text))
        case _TextField.TITLE:
            patch = TaskPatch(title=text)
        case _TextField.DESCRIPTION:
            patch = TaskPatch(description=text)
        case _TextField.PROJECT:
            patch = TaskPatch(project_id=_project_id(text, data.project_refs))
        case _TextField.NOTE:
            return AddNote(task_id=task.id, body=text)
        case _:
            assert_never(field)
    return ChangeTask(task_id=task.id, version=task.version, patch=patch)


class TaskEditor:
    """The edits of the Tasks tab: what each key asks for, and what Enter sends.

    `write` sends a change and raises `MeuteError` when it is refused: a version conflict
    keeps the line open with what was typed, and the next Enter sends the new version.
    """

    def __init__(
        self,
        *,
        write: Callable[[TaskAction], None],
        notice: Callable[[str], None],
        fail: Callable[[str], None],
        data: Callable[[], BoardData],
        local: tzinfo,
    ) -> None:
        self._write = write
        self._notice = notice
        self._fail = fail
        self._data = data
        self._local = local
        self.widget = TaskInput()
        self._edit: _TaskEdit | _NewTask | None = None

    @property
    def editing(self) -> bool:
        """Whether the line or the list is open."""
        return self._edit is not None

    def start(self, key: str, task: Task | None) -> bool:
        """Open the edit of `key` on `task`; `False` when `key` is not an edit key."""
        field = _TEXT_KEYS.get(key) or _CHOICE_KEYS.get(key)
        if field is None:
            return False
        if task is None:
            return True
        if field is _TextField.DESCRIPTION and len(task.description.splitlines()) > 1:
            self._notice(MULTILINE_DESCRIPTION)  # one line would lose the line breaks
        else:
            self._open(_TaskEdit(field, task))
        return True

    def create(self) -> None:
        """Open the quick entry of a new task, with its preview."""
        self._open(_NewTask())
        self.preview("")

    def cancel(self) -> None:
        """Close the line or the list, sending nothing."""
        self._edit = None
        self.widget.close()

    def _open(self, edit: _TaskEdit | _NewTask) -> None:
        self._edit = edit
        self.widget.open(_ask(edit))

    def _now(self) -> datetime:
        return self._data().now or datetime.now(self._local)

    def _quick(self, text: str) -> QuickPreview:
        data = self._data()
        return quick_preview(
            text, now=self._now(), default=data.displayed_project, projects=data.project_refs
        )

    def preview(self, text: str) -> None:
        """Show what the quick entry `text` would create, when a new task is being typed."""
        if isinstance(self._edit, _NewTask):
            self.widget.show_preview(rows_content(preview_lines(self._quick(text), self._now())))

    def submit_text(self, text: str) -> None:
        """Enter on the line."""
        edit = self._edit
        if isinstance(edit, _NewTask):
            if self._quick(text).can_create:  # else the preview already says why not
                self.send(CreateTask(text=text, project=self._data().displayed_project))
        elif isinstance(edit, _TaskEdit) and isinstance(edit.field, _TextField):
            try:
                action = _text_action(edit.field, edit.task, text, self._data())
            except MeuteError as error:
                self._fail(str(error))
                return
            self.send(action)

    def submit_choice(self, index: int) -> None:
        """Enter on the list; `blocked` asks for the reason first."""
        edit = self._edit
        if not isinstance(edit, _TaskEdit) or not isinstance(edit.field, _ChoiceField):
            return
        match edit.field:
            case _ChoiceField.STATUS:
                kind = _STATUSES[index][0]
                if kind is StatusKind.BLOCKED:
                    self._open(_TaskEdit(_TextField.BLOCKED, edit.task))
                    return
                patch = TaskPatch(status=status_from_kind(kind))
            case _ChoiceField.PRIORITY:
                patch = TaskPatch(priority=_PRIORITIES[index])
            case _ChoiceField.POSTPONE:
                patch = TaskPatch(due=postpone(_POSTPONES[index], self._now()))
            case _:
                assert_never(edit.field)
        self.send(ChangeTask(task_id=edit.task.id, version=edit.task.version, patch=patch))

    def send(self, action: TaskAction) -> None:
        """Send `action`; close the edit when it went through, keep it open otherwise."""
        try:
            self._write(action)
        except VersionConflict as conflict:
            self._notice(conflict_text(conflict.current.id))
            if isinstance(self._edit, _TaskEdit):
                self._edit = replace(self._edit, task=conflict.current)
            return
        except NotFound as error:  # deleted elsewhere: nothing left to edit
            self._fail(str(error))
        except MeuteError as error:
            self._fail(str(error))
            return
        if self._edit is not None:
            self.cancel()
