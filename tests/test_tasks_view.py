"""Tests of the Tasks tab model: filters, groups, folding, counters, selection."""

import time
from collections.abc import Sequence
from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st
from syrupy.assertion import SnapshotAssertion

from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, Done, Priority, Review, TaskStatus, Todo
from meute.core.styled import Role, plain
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
    filters_line,
    keep_tasks_selection,
    tasks_line_key,
    tasks_selectable,
)
from support import NOW, at_due, date_due, make_task

MEUTE = ProjectRef(id=ProjectId(1), name="meute")
MODS = ProjectRef(id=ProjectId(2), name="Alpha")
OPEN = frozenset[str]()


def _in(task: Task, ref: ProjectRef | None) -> Task:
    return replace(task, project=ref)


def _texts(view: TasksView) -> list[str]:
    return [plain(line.spans) for line in view.lines]


def _build(
    tasks: Sequence[Task],
    state: TasksState | None = None,
    project: ProjectRef | None = None,
    width: int = 60,
) -> TasksView:
    return build_tasks_view(
        tasks, state or TasksState(collapsed=OPEN), now=NOW, project=project, width=width
    )


def _sample() -> list[Task]:
    return [
        _in(
            make_task(1, due=at_due("2026-10-14T08:30[Europe/Paris]"), priority=Priority.URGENT),
            MEUTE,
        ),
        _in(make_task(2, due=date_due("2026-10-13")), MEUTE),
        _in(make_task(3, due=at_due("2026-10-14T18:00[Europe/Paris]")), None),
        _in(make_task(4, status=Review(), due=date_due("2026-10-14")), MODS),
        _in(make_task(5, due=date_due("2026-10-20")), MEUTE),
        _in(make_task(6), MODS),
        _in(make_task(7, status=Done(), completed_at=NOW), MEUTE),
        _in(make_task(8, status=Done(), completed_at=NOW.replace(day=1)), MEUTE),
        _in(make_task(9, status=Blocked(reason="VPN"), due=date_due("2026-10-14")), None),
    ]


def test_default_state() -> None:
    state = TasksState()
    assert state.scope is TaskScope.ALL
    assert state.grouping is Grouping.URGENCY
    assert state.collapsed == frozenset({"no_due", "done_today"})


def test_urgency_groups_and_order() -> None:
    view = _build(_sample())
    headers = [(line.group, line.band) for line in view.lines if isinstance(line, TaskGroupLine)]
    assert headers == [
        ("overdue", True),
        ("today", False),
        ("upcoming", False),
        ("no_due", False),
        ("done_today", False),
    ]
    assert [t for t in _texts(view) if t.startswith(("▼", "▶"))] == [
        "▼ Overdue (2)",
        "▼ Today (3)",
        "▼ Upcoming (1)",
        "▼ No due date (1)",
        "▼ Done today (1)",
    ]


def test_tasks_order_within_group_and_band() -> None:
    view = _build(_sample())
    ids = [(line.task_id, line.band) for line in view.lines if isinstance(line, TaskLine)]
    assert ids == [
        (TaskId(2), True),
        (TaskId(1), True),
        (TaskId(3), False),
        (TaskId(4), False),
        (TaskId(9), False),
        (TaskId(5), False),
        (TaskId(6), False),
        (TaskId(7), False),
    ]


def test_default_state_folds_no_due_and_done_today() -> None:
    view = _build(_sample(), TasksState())
    texts = _texts(view)
    assert "▶ No due date (1)" in texts
    assert "▶ Done today (1)" in texts
    assert not any(isinstance(line, TaskLine) and line.task_id in (6, 7) for line in view.lines)
    folded = [line.collapsed for line in view.lines if isinstance(line, TaskGroupLine)]
    assert folded == [False, False, False, True, True]


def test_empty_groups_omitted() -> None:
    view = _build([make_task(1)])
    assert _texts(view)[0] == "▼ No due date (1)"
    assert len(view.lines) == 2


def test_no_tasks_message() -> None:
    view = _build([])
    assert [type(line) for line in view.lines] == [TaskInfoLine]
    assert _texts(view) == ["No tasks. Press a to add one."]
    assert (view.open_count, view.overdue_count) == (0, 0)


def test_only_unlisted_done_task_gives_the_message() -> None:
    old = make_task(1, status=Done(), completed_at=NOW.replace(day=1))
    assert _texts(_build([old])) == ["No tasks. Press a to add one."]


def test_filter_floating() -> None:
    view = _build(_sample(), TasksState(scope=TaskScope.FLOATING, collapsed=OPEN))
    ids = [line.task_id for line in view.lines if isinstance(line, TaskLine)]
    assert ids == [TaskId(3), TaskId(9)]


def test_filter_this_project() -> None:
    state = TasksState(scope=TaskScope.THIS_PROJECT, collapsed=OPEN)
    view = _build(_sample(), state, project=MEUTE)
    ids = [line.task_id for line in view.lines if isinstance(line, TaskLine)]
    assert ids == [TaskId(2), TaskId(1), TaskId(5), TaskId(7)]


def test_filter_this_project_matches_by_id_not_name() -> None:
    renamed = ProjectRef(id=MEUTE.id, name="other name")
    state = TasksState(scope=TaskScope.THIS_PROJECT, collapsed=OPEN)
    view = _build(_sample(), state, project=renamed)
    assert len([line for line in view.lines if isinstance(line, TaskLine)]) == 4


def test_filter_this_project_without_project() -> None:
    state = TasksState(scope=TaskScope.THIS_PROJECT)
    view = _build(_sample(), state, project=None)
    assert _texts(view) == ["No project for the displayed session."]
    assert isinstance(view.lines[0], TaskInfoLine)
    assert (view.open_count, view.overdue_count) == (7, 2)


def test_filter_with_no_matching_task() -> None:
    state = TasksState(scope=TaskScope.FLOATING)
    view = _build([_in(make_task(1), MEUTE)], state)
    assert _texts(view) == ["No tasks. Press a to add one."]


def test_counters_ignore_filter_and_folding() -> None:
    state = TasksState(scope=TaskScope.FLOATING)
    view = _build(_sample(), state)
    assert view.open_count == 7
    assert view.overdue_count == 2


def test_counters_exclude_done_tasks() -> None:
    view = _build([make_task(1, status=Done(), completed_at=NOW), make_task(2)])
    assert view.open_count == 1


def test_project_grouping_sorted_without_case_floating_last() -> None:
    state = TasksState(grouping=Grouping.PROJECT, collapsed=OPEN)
    view = _build(_sample(), state)
    headers = [line for line in view.lines if isinstance(line, TaskGroupLine)]
    assert [line.group for line in headers] == ["project:2", "project:1", "floating"]
    assert [t for t in _texts(view) if t.startswith("▼")] == [
        "▼ Alpha (2)",
        "▼ meute (4)",
        "▼ Floating (2)",
    ]
    assert not any(line.band for line in view.lines if not isinstance(line, TaskInfoLine))


def test_project_grouping_collapse_and_sort_inside() -> None:
    state = TasksState(grouping=Grouping.PROJECT, collapsed=frozenset({"project:1"}))
    view = _build(_sample(), state)
    assert "▶ meute (4)" in _texts(view)
    ids = [line.task_id for line in view.lines if isinstance(line, TaskLine)]
    assert ids == [TaskId(4), TaskId(6), TaskId(3), TaskId(9)]


def test_project_name_is_printable() -> None:
    task = _in(make_task(1), ProjectRef(id=ProjectId(3), name="a\x1b[2Jb"))
    state = TasksState(grouping=Grouping.PROJECT, collapsed=OPEN)
    assert "\x1b" not in "".join(_texts(_build([task], state)))


def test_overdue_header_role() -> None:
    view = _build(_sample())
    overdue, today = (
        view.lines[0],
        next(
            line for line in view.lines if isinstance(line, TaskGroupLine) and line.group == "today"
        ),
    )
    assert overdue.spans[0].role is Role.ATTENTION
    assert today.spans[0].role is Role.TITLE


def test_filters_line() -> None:
    line = filters_line(TasksState(), MEUTE, 60)
    assert plain(line) == " all   this project (meute)   floating " + " " * 12 + "f: filter"
    assert len(plain(line)) == 60
    roles = {span.text: span.role for span in line}
    assert roles[" all "] is Role.TAB_ACTIVE
    assert roles[" floating "] is Role.TAB
    assert roles["f: filter"] is Role.DIM


def test_filters_line_active_and_missing_project() -> None:
    state = TasksState(scope=TaskScope.THIS_PROJECT)
    line = filters_line(state, None, 60)
    assert " this project (none) " in plain(line)
    assert {span.text: span.role for span in line}[" this project (none) "] is Role.TAB_ACTIVE
    floating = filters_line(TasksState(scope=TaskScope.FLOATING), None, 60)
    assert {span.text: span.role for span in floating}[" floating "] is Role.TAB_ACTIVE


def test_keys() -> None:
    view = _build(_sample(), TasksState())
    keys = [tasks_line_key(line) for line in view.lines]
    assert keys[0] is None  # expanded header
    assert keys[1] == "task:2"
    assert "group:no_due" in keys
    assert "group:done_today" in keys
    assert tasks_selectable(view) == tuple(i for i, key in enumerate(keys) if key is not None)


def test_info_line_is_not_selectable() -> None:
    view = _build([])
    assert tasks_selectable(view) == ()
    assert keep_tasks_selection("task:1", view, 0) == -1


def test_keep_selection_rules() -> None:
    view = _build(_sample(), TasksState())
    selectable = tasks_selectable(view)
    assert keep_tasks_selection("task:1", view, 0) == view.lines.index(
        next(line for line in view.lines if isinstance(line, TaskLine) and line.task_id == 1)
    )
    assert keep_tasks_selection("task:404", view, 1) == selectable[1]
    assert keep_tasks_selection(None, view, 99) == selectable[-1]
    assert keep_tasks_selection(None, view, -5) == selectable[0]
    assert keep_tasks_selection("task:6", view, 0, old_group="no_due") == next(
        i for i, line in enumerate(view.lines) if tasks_line_key(line) == "group:no_due"
    )


def test_snapshot_urgency(snapshot: SnapshotAssertion) -> None:
    assert _texts(_build(_sample(), TasksState(), width=60)) == snapshot


def test_snapshot_project(snapshot: SnapshotAssertion) -> None:
    state = TasksState(grouping=Grouping.PROJECT, collapsed=OPEN)
    assert _texts(_build(_sample(), state, width=60)) == snapshot


def test_dirty_long_title_lines_have_width() -> None:
    task = replace(make_task(1, due=date_due("2026-10-13")), title="é\x1b\n" * 170, project=MEUTE)
    view = _build([task], width=50)
    line = view.lines[1]
    assert isinstance(line, TaskLine)
    assert len(plain(line.spans)) == 50
    assert plain(line.spans).endswith("yesterday")


def test_500_tasks_build_quickly() -> None:
    tasks = [
        _in(make_task(i, due=date_due(f"2026-10-{1 + i % 28:02d}")), MEUTE if i % 3 else None)
        for i in range(1, 501)
    ]
    state = TasksState(collapsed=OPEN)
    started = time.perf_counter()
    view = _build(tasks, state)
    elapsed = time.perf_counter() - started
    assert len([line for line in view.lines if isinstance(line, TaskLine)]) == 500
    assert elapsed < 0.5


_STATUSES: list[TaskStatus] = [Todo(), Review(), Done(), Blocked(reason="r")]


def _drawn_task(
    task_id: int, status: TaskStatus, day: int | None, ref: ProjectRef | None, *, done_now: bool
) -> Task:
    due = None if day is None else date_due(f"2026-10-{day:02d}")
    task = make_task(task_id, status=status, due=due, completed_at=NOW if done_now else None)
    return replace(task, project=ref)


_task = st.builds(
    _drawn_task,
    st.integers(1, 10_000),
    st.sampled_from(_STATUSES),
    st.none() | st.integers(1, 28),
    st.none() | st.sampled_from([MEUTE, MODS]),
    done_now=st.booleans(),
)


@given(
    tasks=st.lists(_task, max_size=30, unique_by=lambda t: t.id),
    scope=st.sampled_from(TaskScope),
    grouping=st.sampled_from(Grouping),
    collapsed=st.sets(
        st.sampled_from(
            [
                "overdue",
                "today",
                "upcoming",
                "no_due",
                "done_today",
                "project:1",
                "project:2",
                "floating",
            ]
        )
    ),
    project=st.none() | st.just(MEUTE),
    old=st.none() | st.sampled_from(["task:1", "task:5", "group:today", "group:no_due", "junk"]),
    fallback=st.integers(-3, 40),
)
def test_kept_selection_is_minus_one_or_selectable(  # noqa: PLR0913 — one argument per drawn input
    *,
    tasks: list[Task],
    scope: TaskScope,
    grouping: Grouping,
    collapsed: set[str],
    project: ProjectRef | None,
    old: str | None,
    fallback: int,
) -> None:
    state = TasksState(scope=scope, grouping=grouping, collapsed=frozenset(collapsed))
    view = _build(tasks, state, project)
    kept = keep_tasks_selection(old, view, fallback)
    choices = tasks_selectable(view)
    assert kept == -1 if not choices else kept in choices
    assert all(isinstance(view.lines[i], TaskLine | TaskGroupLine) for i in choices)
