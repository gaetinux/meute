"""Urgency buckets, display order and English due formatting (pure functions)."""

from collections.abc import Iterable
from datetime import date, datetime, time, timedelta
from enum import Enum

from meute.core.status import Done, is_open
from meute.core.task import Due, DueAt, DueDate, Task

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class Bucket(Enum):
    """Urgency group of a task in lists (specification section 9.5)."""

    OVERDUE = "overdue"
    TODAY = "today"
    UPCOMING = "upcoming"
    NO_DUE = "no_due"
    DONE_TODAY = "done_today"

    @property
    def label(self) -> str:
        """Human-readable group title."""
        match self:
            case Bucket.OVERDUE:
                return "Overdue"
            case Bucket.TODAY:
                return "Today"
            case Bucket.UPCOMING:
                return "Upcoming"
            case Bucket.NO_DUE:
                return "No due date"
            case Bucket.DONE_TODAY:
                return "Done today"


def _bucket_of_due(due: Due, now: datetime) -> Bucket:
    today = now.date()
    match due:
        case DueDate(day=day):
            if day < today:
                return Bucket.OVERDUE
            return Bucket.TODAY if day == today else Bucket.UPCOMING
        case DueAt(at=at):
            if at < now:
                return Bucket.OVERDUE
            return Bucket.TODAY if at.astimezone(now.tzinfo).date() == today else Bucket.UPCOMING


def bucket_of(task: Task, now: datetime) -> Bucket | None:
    """Return the urgency group of `task`, or `None` when it is not listed.

    Days are read in the time zone of `now`. A done task is listed only when it
    was completed today.
    """
    if isinstance(task.status, Done):
        done = task.completed_at
        if done is not None and done.astimezone(now.tzinfo).date() == now.date():
            return Bucket.DONE_TODAY
        return None
    if task.due is None:
        return Bucket.NO_DUE
    return _bucket_of_due(task.due, now)


def is_overdue(task: Task, now: datetime) -> bool:
    """Return whether `task` is open and past its due date or instant."""
    return is_open(task.status) and bucket_of(task, now) is Bucket.OVERDUE


def _due_instant(due: Due, now: datetime) -> datetime:
    match due:
        case DueDate(day=day):
            return datetime.combine(day, time(23, 59, 59), tzinfo=now.tzinfo)
        case DueAt(at=at):
            return at


def sort_for_display(tasks: Iterable[Task], now: datetime) -> list[Task]:
    """Sort by due instant (a date counts as 23:59:59), then priority, then id.

    Tasks without a due come last.
    """

    def key(task: Task) -> tuple[bool, datetime, int, int]:
        if task.due is None:
            return (True, now, task.priority.rank, task.id)
        return (False, _due_instant(task.due, now), task.priority.rank, task.id)

    return sorted(tasks, key=key)


def _format_day(day: date, now: datetime) -> str:
    today = now.date()
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    text = f"{_DAYS[day.weekday()]} {_MONTHS[day.month - 1]} {day.day}"
    return text if day.year == today.year else f"{text} {day.year}"


def _format_clock(moment: datetime) -> str:
    hour = moment.hour % 12 or 12
    minutes = f":{moment.minute:02d}" if moment.minute else ""
    return f"{hour}{minutes}{'am' if moment.hour < 12 else 'pm'}"  # noqa: PLR2004 — noon


def format_due(due: Due, now: datetime) -> str:
    """Format `due` in English, in the time zone of `now`.

    Examples: `today`, `tomorrow 12pm`, `Fri Oct 16 2:30pm`, `Tue Jan 5 2027`.
    """
    match due:
        case DueDate(day=day):
            return _format_day(day, now)
        case DueAt(at=at):
            local = at.astimezone(now.tzinfo)
            return f"{_format_day(local.date(), now)} {_format_clock(local)}"
