"""The Tasks tab: its cursor, its keys and clicks, the task detail."""

from collections.abc import Callable
from datetime import datetime, tzinfo

from textual.content import Content

from meute.core.board_header import tasks_totals
from meute.core.board_view import TASKS_FOOTER, TASKS_KEYS_HELP, BoardAction, BoardData, ShowSession
from meute.core.session import Session
from meute.core.session_state import is_live
from meute.core.task import TaskId
from meute.core.task_detail import task_detail_lines
from meute.core.tasks_view import TaskGroupLine, TaskInfoLine, TaskLine, filters_line
from meute.tui.tasks_cursor import TasksCursor
from meute.tui.tasks_pane import rows_content, rule, tasks_content


class TasksTab:
    """The Tasks view; the board gives it where to send actions."""

    def __init__(self, *, perform: Callable[[BoardAction], None], local: tzinfo) -> None:
        self._perform = perform
        self._local = local
        self.cursor = TasksCursor(datetime.now(local))

    @property
    def selected(self) -> int:
        """The selected line of the view, -1 when nothing is selectable."""
        return self.cursor.selected

    @property
    def overdue_count(self) -> int:
        """The overdue tasks, whatever the filter and the folds."""
        return self.cursor.view.overdue_count

    def totals(self) -> str:
        """The open and overdue tasks."""
        view = self.cursor.view
        return tasks_totals(view.open_count, view.overdue_count)

    def rebuild(self, data: BoardData, width: int) -> None:  # noqa: ARG002 — the lines follow `fit`
        """Take the new data, keeping the selection and the folds."""
        self.cursor.rebuild(data, data.now or datetime.now(self._local))

    def fit(self, width: int) -> bool:
        """Lay the lines out for `width`; `True` when that changed them."""
        if width == self.cursor.width:
            return False
        self.cursor.resize(width)
        return True

    def handle_key(self, key: str) -> bool:
        """Apply `key`; `False` when the board should deal with it."""
        if self.cursor.handle_key(key):
            return True
        if key == "enter":
            self._enter()
            return True
        return False

    def _enter(self) -> None:
        """Unfold a folded heading, or show the most recent live session of the task."""
        cursor = self.cursor
        group = cursor.group_at(cursor.selected)
        task = cursor.task_at(cursor.selected)
        if task is None:
            if group is not None:
                cursor.fold(group, fold=False)
            return
        live = [s for s in self._linked(task.id) if is_live(s.state)]
        if live:
            latest = max(live, key=lambda session: session.last_activity_at)
            self._perform(ShowSession(session_id=latest.id))

    def _linked(self, task_id: TaskId) -> list[Session]:
        data = self.cursor.data
        rows = (*data.sessions, *data.ended)
        linked = [row.session for row in rows if row.session.task_id == task_id]
        return sorted(linked, key=lambda session: session.last_activity_at, reverse=True)

    def click(self, y: int, x: int) -> None:
        """Select the task at row `y`, or fold the heading there."""
        _ = x
        line = self.cursor.view.lines[y] if 0 <= y < len(self.cursor.view.lines) else None
        match line:
            case TaskLine():
                self.cursor.selected = y
            case TaskGroupLine():
                self.cursor.fold(line.group, fold=not line.collapsed)
            case TaskInfoLine() | None:
                pass

    def lines(self, *, focused: bool) -> Content:
        """The grouped tasks, the selected one highlighted."""
        cursor = self.cursor
        return tasks_content(cursor.view, cursor.selected, focused=focused, width=cursor.width)

    def quota(self) -> Content | None:
        """The filter row and a rule, in the slot above the list."""
        cursor = self.cursor
        filters = filters_line(cursor.state, cursor.data.displayed_project, cursor.width)
        return rows_content([filters, rule(cursor.width)])

    def details(self, width: int) -> Content | None:
        """The selected task's detail, when a task is selected."""
        cursor = self.cursor
        task = cursor.task_at(cursor.selected)
        if task is None:
            return None
        data = cursor.data
        repo = next((r for r in data.repos if r.id == task.repo_id), None)
        rows = task_detail_lines(
            task,
            notes=data.notes.get(task.id, ()),
            sessions=self._linked(task.id),
            repo=repo,
            now=cursor.now,
            home=data.home,
            width=width,
        )
        return rows_content(rows)

    def prompt(self) -> str | None:
        """No confirmation yet."""
        return None

    def footer(self) -> str:
        """The one-line keys."""
        return TASKS_FOOTER

    def keys_help(self) -> str:
        """The full list of keys."""
        return TASKS_KEYS_HELP
