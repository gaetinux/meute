"""Pure rendering of task lines and details."""

from dataclasses import replace

from meute.cli.render import preview_line, task_detail, task_line
from meute.core.project import ProjectId, ProjectRef
from meute.core.quick_add import QuickAdd
from meute.core.status import Blocked, Done, Priority
from support import FIXED, NOW, date_due, make_task


def test_detail_of_blocked_task_with_description_and_no_notes() -> None:
    task = replace(
        make_task(3, status=Blocked(reason="waiting for CI")), description="Ship it", version=2
    )
    assert task_detail(task, [], NOW) == (
        "#3 task 3\n"
        "Status: blocked (waiting for CI)\n"
        "Priority: normal\n"
        "Due: —\n"
        "Project: —\n"
        "Version: 2\n"
        "Created: 2026-10-14 10:30\n"
        "Updated: 2026-10-14 10:30\n"
        "Description: Ship it"
    )


def test_detail_of_done_task_shows_completion_after_update() -> None:
    task = make_task(4, status=Done(), completed_at=FIXED)
    assert task_detail(task, [], NOW) == (
        "#4 task 4\n"
        "Status: done\n"
        "Priority: normal\n"
        "Due: —\n"
        "Project: —\n"
        "Version: 1\n"
        "Created: 2026-10-14 10:30\n"
        "Updated: 2026-10-14 10:30\n"
        "Completed: 2026-10-14 10:30"
    )


def test_preview_line_with_project_has_no_identifier() -> None:
    parsed = QuickAdd(
        title="Pay", project="meute", priority=Priority.HIGH, due=date_due("2026-10-15")
    )
    assert preview_line(parsed, NOW) == "· ! Pay @meute · tomorrow"


def test_done_task_line_shows_its_due_without_overdue() -> None:
    task = replace(
        make_task(5, status=Done(), due=date_due("2026-10-10"), completed_at=FIXED),
        project=ProjectRef(id=ProjectId(1), name="meute"),
    )
    assert task_line(task, NOW) == "#5 ✓ task 5 @meute · Sat Oct 10"
