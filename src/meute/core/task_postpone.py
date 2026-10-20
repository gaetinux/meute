"""The quick postpones offered for a task's due."""

from datetime import UTC, datetime, time, timedelta
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


def _tonight(now: datetime) -> Due:
    today = local_due(now.date(), _EVENING, now)
    return today if today.at > now else local_due(now.date() + timedelta(days=1), _EVENING, now)


def _monday(now: datetime) -> Due:
    ahead = (_MONDAY - now.weekday()) % _WEEK
    first = local_due(now.date() + timedelta(days=ahead), _MORNING, now)
    return (
        first
        if first.at > now
        else local_due(
            first.at.astimezone(now.tzinfo).date() + timedelta(days=_WEEK), _MORNING, now
        )
    )


def postpone(choice: Postpone, now: datetime) -> Due | None:
    """Return the new due for `choice`, or `None` to clear it.

    Times are wall-clock in the time zone of `now` (a time in the spring DST gap shifts forward
    by an hour); `+1h` is real time. "Monday 9am" is the first Monday 09:00 strictly after `now`.
    """
    match choice:
        case Postpone.HOUR:
            return DueAt(at=now.astimezone(UTC) + timedelta(hours=1))
        case Postpone.TONIGHT:
            return _tonight(now)
        case Postpone.TOMORROW:
            return local_due(now.date() + timedelta(days=1), _MORNING, now)
        case Postpone.MONDAY:
            return _monday(now)
        case Postpone.CLEAR:
            return None
        case _:
            assert_never(choice)
