"""The Tasks tab model: filters, urgency or project groups, folding, counters and selection."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import assert_never

from meute.core.project import ProjectRef
from meute.core.status import Done
from meute.core.styled import Role, Span, StyledLine, fit
from meute.core.task import Task, TaskId
from meute.core.task_line import task_line
from meute.core.text import one_line
from meute.core.views import Bucket, bucket_of, is_overdue, sort_for_display

_NAME_LIMIT = 40
_FLOATING = "floating"
EMPTY_TEXT = "No tasks. Press a to add one."
NO_PROJECT_TEXT = "No project for the displayed session."


class TaskScope(Enum):
    """Which tasks the tab lists."""

    ALL = "all"
    THIS_PROJECT = "this_project"
    FLOATING = "floating"


class Grouping(Enum):
    """How the listed tasks are grouped."""

    URGENCY = "urgency"
    PROJECT = "project"


@dataclass(frozen=True, slots=True)
class TasksState:
    """The user's choices: filter, grouping and folded groups.

    Group keys are `Bucket.value` (`overdue`, `no_due`, ...), `project:{id}` or `floating`.
    """

    scope: TaskScope = TaskScope.ALL
    grouping: Grouping = Grouping.URGENCY
    collapsed: frozenset[str] = field(default_factory=lambda: frozenset({"no_due", "done_today"}))


@dataclass(frozen=True, slots=True)
class TaskGroupLine:
    """A group heading; a folded one is selectable."""

    group: str
    spans: StyledLine
    collapsed: bool
    band: bool


@dataclass(frozen=True, slots=True)
class TaskLine:
    """One task."""

    task_id: TaskId
    spans: StyledLine
    band: bool


@dataclass(frozen=True, slots=True)
class TaskInfoLine:
    """A line of information, never selectable."""

    spans: StyledLine


TasksLine = TaskGroupLine | TaskLine | TaskInfoLine


@dataclass(frozen=True, slots=True)
class TasksView:
    """The lines of the tab and the counters of its title.

    `open_count` and `overdue_count` cover all the given tasks, whatever the filter and the
    folding: the title always tells how much is open and late.
    """

    lines: tuple[TasksLine, ...]
    open_count: int
    overdue_count: int


def _keep(task: Task, scope: TaskScope, project: ProjectRef | None) -> bool:
    match scope:
        case TaskScope.ALL:
            return True
        case TaskScope.FLOATING:
            return task.project is None
        case TaskScope.THIS_PROJECT:
            return (
                project is not None and task.project is not None and task.project.id == project.id
            )
        case _:
            assert_never(scope)


def _group_line(
    key: str, title: str, count: int, *, state: TasksState, urgent: bool
) -> TaskGroupLine:
    folded = key in state.collapsed
    role = Role.ATTENTION if urgent else Role.TITLE
    text = f"{'▶' if folded else '▼'} {title} ({count})"
    return TaskGroupLine(group=key, spans=(Span(text, role),), collapsed=folded, band=urgent)


def _emit(
    groups: Sequence[tuple[str, str, list[Task], bool]],
    state: TasksState,
    line_of: Callable[[Task], StyledLine],
) -> list[TasksLine]:
    lines: list[TasksLine] = []
    for key, title, members, urgent in groups:
        header = _group_line(key, title, len(members), state=state, urgent=urgent)
        lines.append(header)
        if not header.collapsed:
            lines.extend(TaskLine(task_id=t.id, spans=line_of(t), band=urgent) for t in members)
    return lines


def _urgency_groups(
    tasks: Sequence[Task], now: datetime
) -> list[tuple[str, str, list[Task], bool]]:
    by_bucket: dict[Bucket, list[Task]] = {bucket: [] for bucket in Bucket}
    for task in sort_for_display(tasks, now):
        bucket = bucket_of(task, now)
        if bucket is not None:
            by_bucket[bucket].append(task)
    return [
        (bucket.value, bucket.label, members, bucket is Bucket.OVERDUE)
        for bucket, members in by_bucket.items()
        if members
    ]


def _project_groups(
    tasks: Sequence[Task], now: datetime
) -> list[tuple[str, str, list[Task], bool]]:
    named: dict[ProjectRef, list[Task]] = {}
    floating: list[Task] = []
    for task in sort_for_display(tasks, now):
        if bucket_of(task, now) is None:
            continue
        if task.project is None:
            floating.append(task)
        else:
            named.setdefault(task.project, []).append(task)
    ordered = sorted(named.items(), key=lambda item: (item[0].name.casefold(), item[0].id))
    groups = [
        (f"project:{ref.id}", one_line(ref.name, _NAME_LIMIT), members, False)
        for ref, members in ordered
    ]
    if floating:
        groups.append((_FLOATING, "Floating", floating, False))
    return groups


def build_tasks_view(
    tasks: Sequence[Task],
    state: TasksState,
    *,
    now: datetime,
    project: ProjectRef | None,
    width: int,
) -> TasksView:
    """Build the lines of the Tasks tab for `tasks`, filtered and grouped as `state` says.

    `project` is the project of the displayed session, used by the "this project" filter.
    """
    open_count = sum(1 for task in tasks if not isinstance(task.status, Done))
    overdue_count = sum(1 for task in tasks if is_overdue(task, now))
    counters = (open_count, overdue_count)
    if state.scope is TaskScope.THIS_PROJECT and project is None:
        return TasksView((TaskInfoLine((Span(NO_PROJECT_TEXT, Role.DIM),)),), *counters)
    shown = [task for task in tasks if _keep(task, state.scope, project)]
    match state.grouping:
        case Grouping.URGENCY:
            groups = _urgency_groups(shown, now)
        case Grouping.PROJECT:
            groups = _project_groups(shown, now)
        case _:
            assert_never(state.grouping)
    lines = _emit(groups, state, lambda task: task_line(task, now, width))
    if not lines:
        lines = [TaskInfoLine((Span(EMPTY_TEXT, Role.DIM),))]
    return TasksView(tuple(lines), *counters)


def filters_line(state: TasksState, project: ProjectRef | None, width: int) -> StyledLine:
    """Return the filter row: ` all `, ` this project (name) `, ` floating `, then `f: filter`.

    The active filter has the `TAB_ACTIVE` role; `f: filter` sticks to the right edge.
    """
    name = "none" if project is None else one_line(project.name, _NAME_LIMIT)
    labels = (
        (TaskScope.ALL, "all"),
        (TaskScope.THIS_PROJECT, f"this project ({name})"),
        (TaskScope.FLOATING, "floating"),
    )
    left: list[Span] = []
    for scope, label in labels:
        if left:
            left.append(Span(" "))
        role = Role.TAB_ACTIVE if scope is state.scope else Role.TAB
        left.append(Span(f" {label} ", role))
    return fit(tuple(left), (Span("f: filter", Role.DIM),), width)


def tasks_line_key(line: TasksLine) -> str | None:
    """Return the key that identifies a selectable line across refreshes; None for the others."""
    match line:
        case TaskLine():
            return f"task:{line.task_id}"
        case TaskGroupLine():
            return f"group:{line.group}" if line.collapsed else None
        case TaskInfoLine():
            return None
        case _:
            assert_never(line)


def tasks_selectable(view: TasksView) -> tuple[int, ...]:
    """Return the indexes of the selectable lines: tasks and folded group headings."""
    return tuple(i for i, line in enumerate(view.lines) if tasks_line_key(line) is not None)


def keep_tasks_selection(
    old_key: str | None, view: TasksView, fallback: int, *, old_group: str | None = None
) -> int:
    """Return the line index to select: the line with `old_key`, else the `fallback`-th choice.

    When the line is gone because its group `old_group` is now folded, that group's heading is
    selected. `fallback` is a position among the selectable lines, clamped to them. Returns -1
    when nothing can be selected: never an information line or an expanded heading.
    """
    choices = tasks_selectable(view)
    if not choices:
        return -1
    for wanted in (old_key, None if old_group is None else f"group:{old_group}"):
        for index in choices:
            if wanted is not None and tasks_line_key(view.lines[index]) == wanted:
                return index
    return choices[min(max(fallback, 0), len(choices) - 1)]
