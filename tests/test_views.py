from datetime import UTC, datetime, timedelta

import pytest

from meute.core.status import Done, Priority, Review
from meute.core.task import Due, DueAt, Task
from meute.core.views import Bucket, bucket_of, format_due, is_overdue, sort_for_display
from support import NOW, at_due, date_due, make_task

P = "[Europe/Paris]"


@pytest.mark.parametrize(
    ("task", "bucket"),
    [
        (make_task(1, due=date_due("2026-10-13")), Bucket.OVERDUE),
        (make_task(2, due=at_due(f"2026-10-14T09:00{P}")), Bucket.OVERDUE),
        (make_task(3, due=date_due("2026-10-14")), Bucket.TODAY),
        (make_task(4, due=at_due(f"2026-10-14T18:00{P}")), Bucket.TODAY),
        (make_task(5, due=date_due("2026-10-15")), Bucket.UPCOMING),
        (make_task(6), Bucket.NO_DUE),
        (
            make_task(7, status=Done(), completed_at=datetime(2026, 10, 14, 7, 0, tzinfo=UTC)),
            Bucket.DONE_TODAY,
        ),
        # 23:30 UTC on the 13th is 01:30 in Paris on the 14th
        (
            make_task(8, status=Done(), completed_at=datetime(2026, 10, 13, 23, 30, tzinfo=UTC)),
            Bucket.DONE_TODAY,
        ),
        (
            make_task(9, status=Done(), completed_at=datetime(2026, 10, 13, 7, 0, tzinfo=UTC)),
            None,
        ),
        (make_task(10, due=date_due("2026-10-13"), status=Review()), Bucket.OVERDUE),
    ],
)
def test_buckets_follow_rules(task: Task, bucket: Bucket | None) -> None:
    assert bucket_of(task, NOW) == bucket


def test_deadline_exactly_now_is_not_overdue() -> None:
    assert not is_overdue(make_task(1, due=DueAt(at=NOW)), NOW)
    assert is_overdue(make_task(1, due=DueAt(at=NOW - timedelta(seconds=1))), NOW)
    assert not is_overdue(make_task(1, due=date_due("2026-10-13"), status=Done()), NOW)


def test_sort_by_due_then_priority_then_id() -> None:
    tasks = [
        make_task(1, priority=Priority.URGENT),
        make_task(2, due=date_due("2026-10-15"), priority=Priority.LOW),
        make_task(3, due=date_due("2026-10-15"), priority=Priority.HIGH),
        make_task(4, due=at_due(f"2026-10-15T09:00{P}"), priority=Priority.LOW),
    ]
    assert [t.id for t in sort_for_display(tasks, NOW)] == [4, 3, 2, 1]


@pytest.mark.parametrize(
    ("due", "text"),
    [
        (date_due("2026-10-14"), "today"),
        (date_due("2026-10-15"), "tomorrow"),
        (date_due("2026-10-19"), "Mon Oct 19"),
        (date_due("2027-01-05"), "Tue Jan 5 2027"),
        (at_due(f"2026-10-14T18:00{P}"), "today 6pm"),
        (at_due(f"2026-10-16T14:30{P}"), "Fri Oct 16 2:30pm"),
        (at_due(f"2026-10-19T00:00{P}"), "Mon Oct 19 12am"),
        (at_due(f"2026-10-15T12:00{P}"), "tomorrow 12pm"),
    ],
)
def test_due_formatting_in_english(due: Due, text: str) -> None:
    assert format_due(due, NOW) == text


def test_due_at_is_shown_in_local_time_across_dst() -> None:
    due = DueAt(at=datetime(2026, 10, 25, 1, 30, tzinfo=UTC))
    assert format_due(due, NOW) == "Sun Oct 25 2:30am"


def test_bucket_labels() -> None:
    assert [b.label for b in Bucket] == [
        "Overdue",
        "Today",
        "Upcoming",
        "No due date",
        "Done today",
    ]
