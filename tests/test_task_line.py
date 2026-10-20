"""Tests of the task line and the short due texts of the Tasks tab."""

from dataclasses import replace
from datetime import timedelta

import pytest

from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, Done, InProgress, Priority, Review, TaskStatus, Todo
from meute.core.styled import Role, plain
from meute.core.task import Due, DueAt, Task
from meute.core.task_line import due_short, task_line
from meute.core.views import format_clock
from support import NOW, at_due, date_due, make_task

REF = ProjectRef(id=ProjectId(1), name="meute")


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (at_due("2026-10-14T08:30[Europe/Paris]"), ("2h late", Role.LATE)),
        (at_due("2026-10-14T10:29[Europe/Paris]"), ("1m late", Role.LATE)),
        (at_due("2026-10-11T10:30[Europe/Paris]"), ("3d late", Role.LATE)),
        (at_due("2026-10-14T09:30[Europe/Paris]"), ("1h late", Role.LATE)),
        (date_due("2026-10-13"), ("yesterday", Role.LATE)),
        (date_due("2026-10-10"), ("4d late", Role.LATE)),
        (date_due("2026-02-14"), ("242d late", Role.LATE)),
        (at_due("2026-10-14T18:00[Europe/Paris]"), ("6pm", Role.DIM)),
        (at_due("2026-10-14T23:59[Europe/Paris]"), ("11:59pm", Role.DIM)),
        (date_due("2026-10-14"), ("today", Role.DIM)),
        (at_due("2026-10-15T00:00[Europe/Paris]"), ("tomorrow 12am", Role.DIM)),
        (at_due("2099-01-05T09:00[Europe/Paris]"), ("Mon Jan 5 2099 9am", Role.DIM)),
        (date_due("2026-10-16"), ("Fri Oct 16", Role.DIM)),
    ],
)
def test_due_short(due: Due, expected: tuple[str, Role]) -> None:
    assert due_short(make_task(1, due=due), NOW) == expected


def test_due_short_at_midnight_boundary() -> None:
    midnight = NOW.replace(hour=0, minute=0)
    assert due_short(make_task(1, due=at_due("2026-10-14T00:00[Europe/Paris]")), midnight) == (
        "12am",
        Role.DIM,
    )


def test_due_short_under_a_minute_late() -> None:
    task = make_task(1, due=DueAt(at=NOW - timedelta(seconds=30)))
    assert due_short(task, NOW) == ("late", Role.LATE)


def test_due_short_blocked_wins_over_due() -> None:
    task = make_task(1, status=Blocked(reason="waiting for VPN"), due=date_due("2026-10-01"))
    assert due_short(task, NOW) == ("blocked: waiting for VPN", Role.BLOCKED)


def test_due_short_blocked_reason_is_one_printable_line() -> None:
    task = make_task(1, status=Blocked(reason="a\x1b[31m\nb"))
    text, _ = due_short(task, NOW) or ("", Role.PLAIN)
    assert "\x1b" not in text
    assert "\n" not in text


def test_due_short_review_without_due() -> None:
    assert due_short(make_task(1, status=Review()), NOW) == ("in review", Role.REVIEW)


def test_due_short_review_with_due_shows_the_due() -> None:
    task = make_task(1, status=Review(), due=at_due("2026-10-14T18:00[Europe/Paris]"))
    assert due_short(task, NOW) == ("6pm", Role.DIM)


@pytest.mark.parametrize("status", [Todo(), InProgress()])
def test_due_short_without_due_is_none(status: TaskStatus) -> None:
    assert due_short(make_task(1, status=status), NOW) is None


def test_due_short_done_is_none_even_when_past_due() -> None:
    task = make_task(1, status=Done(), due=date_due("2026-10-01"), completed_at=NOW)
    assert due_short(task, NOW) is None


def test_format_clock_is_public() -> None:
    assert format_clock(NOW) == "10:30am"


def _with_project(task: Task, ref: ProjectRef | None) -> Task:
    return replace(task, project=ref)


def test_task_line_layout_and_roles() -> None:
    task = _with_project(
        make_task(1, priority=Priority.URGENT, due=at_due("2026-10-14T08:30[Europe/Paris]")), REF
    )
    line = task_line(task, NOW, 40)
    assert plain(line) == "  · !! task 1  @meute            2h late"
    assert len(plain(line)) == 40
    roles = {span.text: span.role for span in line}
    assert roles["  ·"] == Role.DIM
    assert roles["!!"] == Role.HIGH
    assert roles["  @meute"] == Role.KIND
    assert roles["2h late"] == Role.LATE


def test_task_line_floating_and_high_marker() -> None:
    task = make_task(1, priority=Priority.HIGH, status=InProgress())
    line = task_line(task, NOW, 30)
    assert plain(line) == "  » !  task 1  (floating)     "
    roles = {span.text: span.role for span in line}
    assert roles["  »"] == Role.RUNNING
    assert roles["! "] == Role.WARN
    assert roles["  (floating)"] == Role.DIM


@pytest.mark.parametrize(
    ("status", "symbol", "role"),
    [
        (Todo(), "·", Role.DIM),
        (InProgress(), "»", Role.RUNNING),
        (Blocked(reason="x"), "✕", Role.BLOCKED),
        (Review(), "◎", Role.REVIEW),
        (Done(), "✓", Role.OK),
    ],
)
def test_task_line_symbols(status: TaskStatus, symbol: str, role: Role) -> None:
    line = task_line(make_task(1, status=status), NOW, 30)
    assert line[0] == type(line[0])(f"  {symbol}", role)


def test_task_line_long_dirty_title_keeps_width_and_due() -> None:
    title = ("x\x1b[2J\n\t" * 100)[:500]
    task = replace(make_task(1, due=date_due("2026-10-13")), title=title, project=REF)
    for width in (72, 40, 20):
        line = task_line(task, NOW, width)
        text = plain(line)
        assert len(text) == width
        assert text.endswith("yesterday")
        assert "\x1b" not in text
        assert "\n" not in text
        assert "…" in text


def test_task_line_old_due_text_is_not_lost_by_a_late_age() -> None:
    task = make_task(1, due=at_due("2026-10-14T10:00[Europe/Paris]"))
    assert plain(task_line(task, NOW, 40)).endswith("30m late")
