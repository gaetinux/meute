"""Tests of the quick postpones of a task."""

from datetime import timedelta

import pytest

from meute.core.instants import parse_zoned
from meute.core.task import DueAt
from meute.core.task_postpone import Postpone, postpone
from support import NOW, at_due


def test_labels() -> None:
    assert [p.value for p in Postpone] == [
        "+1h",
        "tonight 6pm",
        "tomorrow 9am",
        "Monday 9am",
        "clear",
    ]


@pytest.mark.parametrize(
    ("now", "choice", "expected"),
    [
        ("2026-10-14T10:30[Europe/Paris]", Postpone.HOUR, "2026-10-14T11:30[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.TONIGHT, "2026-10-14T18:00[Europe/Paris]"),
        ("2026-10-14T18:30[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T18:00[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T23:59[Europe/Paris]", Postpone.TONIGHT, "2026-10-15T18:00[Europe/Paris]"),
        ("2026-10-14T23:59[Europe/Paris]", Postpone.TOMORROW, "2026-10-15T09:00[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.TOMORROW, "2026-10-15T09:00[Europe/Paris]"),
        ("2026-10-14T10:30[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        ("2026-10-19T08:00[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        ("2026-10-19T09:00[Europe/Paris]", Postpone.MONDAY, "2026-10-26T09:00[Europe/Paris]"),
        ("2026-10-18T23:59[Europe/Paris]", Postpone.MONDAY, "2026-10-19T09:00[Europe/Paris]"),
        # The night before the switch to summer time: the day is 23 hours long.
        ("2026-03-28T20:00[Europe/Paris]", Postpone.TOMORROW, "2026-03-29T09:00[Europe/Paris]"),
        ("2026-03-28T20:00[Europe/Paris]", Postpone.HOUR, "2026-03-28T21:00[Europe/Paris]"),
        ("2026-03-29T01:30[Europe/Paris]", Postpone.HOUR, "2026-03-29T03:30[Europe/Paris]"),
        ("2026-03-29T09:30[Europe/Paris]", Postpone.TONIGHT, "2026-03-29T18:00[Europe/Paris]"),
        ("2026-03-27T10:00[Europe/Paris]", Postpone.MONDAY, "2026-03-30T09:00[Europe/Paris]"),
    ],
)
def test_postpone(now: str, choice: Postpone, expected: str) -> None:
    assert postpone(choice, parse_zoned(now)) == at_due(expected)


def test_hour_is_real_time_across_the_switch() -> None:
    now = parse_zoned("2026-03-29T01:30[Europe/Paris]")
    due = postpone(Postpone.HOUR, now)
    assert isinstance(due, DueAt)
    assert due.at - now == timedelta(hours=1)


def test_clear() -> None:
    assert postpone(Postpone.CLEAR, NOW) is None
