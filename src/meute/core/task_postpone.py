"""The quick postpones offered for a task's due."""

from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import assert_never

from meute.core.due_parse import local_due
from meute.core.task import Due, DueAt

_EVENING = time(18, 0)
_MORNING = time(9, 0)
_MONDAY = 0
_WEEK = 7


class Postpone(Enum):
    """A quick postpone; the value is the label shown in the menu."""

    HOUR = "+1h"
    TONIGHT = "tonight 6pm"
    TOMORROW = "tomorrow 9am"
    MONDAY = "Monday 9am"
    CLEAR = "clear"


def _next_after(day: date, at: time, now: datetime, *, step_days: int) -> Due:
    """Return `day` at `at`, or `step_days` later when that is not strictly after `now`."""
    first = local_due(day, at, now)
    return first if first.at > now else local_due(day + timedelta(days=step_days), at, now)


def postpone(choice: Postpone, now: datetime) -> Due | None:
    """Return the new due for `choice`, or `None` to clear it.

    Times are wall-clock in the time zone of `now` (a time in the spring DST gap shifts forward
    by an hour); `+1h` is real time. "Monday 9am" is the first Monday 09:00 strictly after `now`.
    """
    match choice:
        case Postpone.HOUR:
            return DueAt(at=now.astimezone(UTC) + timedelta(hours=1))
        case Postpone.TONIGHT:
            return _next_after(now.date(), _EVENING, now, step_days=1)
        case Postpone.TOMORROW:
            return local_due(now.date() + timedelta(days=1), _MORNING, now)
        case Postpone.MONDAY:
            ahead = (_MONDAY - now.weekday()) % _WEEK
            monday = now.date() + timedelta(days=ahead)
            return _next_after(monday, _MORNING, now, step_days=_WEEK)
        case Postpone.CLEAR:
            return None
        case _:
            assert_never(choice)
