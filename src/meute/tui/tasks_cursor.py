"""The Tasks view's navigation: filter, grouping, folds, the lines and the selected one."""

from dataclasses import replace
from datetime import datetime

from meute.core.board_view import BoardData
from meute.core.task import Task, TaskId
from meute.core.tasks_view import (
    Grouping,
    TaskGroupLine,
    TaskInfoLine,
    TaskLine,
    TaskScope,
    TasksState,
    TasksView,
    build_tasks_view,
    keep_tasks_selection,
    tasks_line_key,
    tasks_selectable,
)

DEFAULT_WIDTH = 72
_NEXT_SCOPE = {
    TaskScope.ALL: TaskScope.THIS_PROJECT,
    TaskScope.THIS_PROJECT: TaskScope.FLOATING,
    TaskScope.FLOATING: TaskScope.ALL,
}
_NEXT_GROUPING = {Grouping.URGENCY: Grouping.PROJECT, Grouping.PROJECT: Grouping.URGENCY}
_EMPTY = BoardData(sessions=(), repos=(), orphans=(), home=None)


class TasksCursor:
    """The view state, the lines it gives and the selected line, kept across reloads."""

    def __init__(self, now: datetime, width: int = DEFAULT_WIDTH) -> None:
        self.width = width
        self.state = TasksState()
        self.data = _EMPTY
        self.now = now
        self.view = self._build()
        self.selected = -1  # a line index of the view; -1: nothing selectable

    def handle_key(self, key: str) -> bool:
        """Apply a navigation or view key; return `False` when `key` is not one."""
        if key in {"up", "k"}:
            self.move(-1)
        elif key in {"down", "j"}:
            self.move(1)
        elif key == "f":
            self.set_state(replace(self.state, scope=_NEXT_SCOPE[self.state.scope]))
        elif key == "g":
            self.set_state(replace(self.state, grouping=_NEXT_GROUPING[self.state.grouping]))
        elif key in {"space", "left", "right"}:
            group = self.group_at(self.selected)
            if group is not None:
                folded = group in self.state.collapsed
                self.fold(group, fold=not folded if key == "space" else key == "left")
        else:
            return False
        return True

    def group_at(self, index: int) -> str | None:
        """Return the group of line `index` (a heading or one of its tasks), else `None`."""
        return self._groups[index] if 0 <= index < len(self._groups) else None

    def task_at(self, index: int) -> Task | None:
        """Return the task on line `index`, or `None`."""
        lines = self.view.lines
        line = lines[index] if 0 <= index < len(lines) else None
        if not isinstance(line, TaskLine):
            return None
        return self._tasks.get(line.task_id)

    def resize(self, width: int) -> None:
        """Rebuild the view for a board `width` columns wide, keeping the selection."""
        if width != self.width:
            self.width = width
            self.rebuild(self.data, self.now)

    def move(self, delta: int) -> None:
        """Move the selection by `delta` selectable lines, stopping at both ends."""
        choices = tasks_selectable(self.view)
        if choices:
            position = choices.index(self.selected) if self.selected in choices else 0
            self.selected = choices[min(max(position + delta, 0), len(choices) - 1)]

    def fold(self, group: str, *, fold: bool) -> None:
        """Fold or unfold `group`; the selection moves to its header, or into it from there."""
        if fold == (group in self.state.collapsed):
            return
        header_selected = self._selected_key() == f"group:{group}"
        inside = self.group_at(self.selected) == group
        collapsed = self.state.collapsed | {group} if fold else self.state.collapsed - {group}
        self.set_state(
            replace(self.state, collapsed=collapsed), old_group=group if fold and inside else None
        )
        if not fold and header_selected:
            members = (
                i
                for i in tasks_selectable(self.view)
                if self.group_at(i) == group and isinstance(self.view.lines[i], TaskLine)
            )
            self.selected = next(members, self.selected)

    def set_state(self, state: TasksState, *, old_group: str | None = None) -> None:
        """Switch to `state` and rebuild the view from the same data."""
        self.state = state
        self.rebuild(self.data, self.now, old_group=old_group)

    def rebuild(self, data: BoardData, now: datetime, *, old_group: str | None = None) -> None:
        """Rebuild the view, keeping the selected line when it is still there."""
        choices = tasks_selectable(self.view)
        position = choices.index(self.selected) if self.selected in choices else 0
        old_key = self._selected_key()
        self.data, self.now = data, now
        self.view = self._build()
        self.selected = keep_tasks_selection(old_key, self.view, position, old_group=old_group)

    def _build(self) -> TasksView:
        view = build_tasks_view(
            self.data.tasks,
            self.state,
            now=self.now,
            project=self.data.displayed_project,
            width=self.width,
        )
        # The first task of an id wins, as a scan of the data would find it.
        self._tasks: dict[TaskId, Task] = {}
        for task in self.data.tasks:
            _ = self._tasks.setdefault(task.id, task)
        self._groups = _line_groups(view)
        return view

    def _selected_key(self) -> str | None:
        lines = self.view.lines
        return tasks_line_key(lines[self.selected]) if 0 <= self.selected < len(lines) else None


def _line_groups(view: TasksView) -> tuple[str | None, ...]:
    """Return the group of each line: its heading's or the one above it; None for information."""
    groups: list[str | None] = []
    current: str | None = None
    for line in view.lines:
        if isinstance(line, TaskGroupLine):
            current = line.group
        groups.append(None if isinstance(line, TaskInfoLine) else current)
    return tuple(groups)
