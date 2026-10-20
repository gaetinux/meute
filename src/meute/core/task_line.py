"""One task as a styled line of the Tasks tab, and its short due text."""

from datetime import datetime
from typing import assert_never

from meute.core.sessions_view_text import age_text
from meute.core.status import Blocked, Done, Review, StatusKind, status_kind
from meute.core.styled import Role, Span, StyledLine, fit
from meute.core.task import DueAt, DueDate, Task
from meute.core.text import one_line
from meute.core.views import Bucket, bucket_of, format_clock, format_due

_TEXT_LIMIT = 1000
_NAME_LIMIT = 40


def _late_text(task: Task, now: datetime) -> str:
    match task.due:
        case DueAt(at=at):
            age = age_text(at, now)
            return "late" if age == "now" else f"{age} late"
        case DueDate(day=day):
            days = (now.date() - day).days
            return "yesterday" if days == 1 else f"{days}d late"
        case None:
            return "late"
        case _:
            assert_never(task.due)


def _today_text(task: Task, now: datetime) -> str:
    match task.due:
        case DueAt(at=at):
            return format_clock(at.astimezone(now.tzinfo))
        case DueDate() | None:
            return "today"
        case _:
            assert_never(task.due)


def due_short(task: Task, now: datetime) -> tuple[str, Role] | None:
    """Return the short text and role shown at the right of a task line, or `None`.

    A blocked task shows its reason, whatever its due. A done task shows nothing. Otherwise:
    `2h late` / `3d late` (an instant) or `yesterday` / `4d late` (a date) when overdue; the
    time (`6pm`) or `today` when due today; the full due when upcoming; `in review` for a task
    in review without a due.
    """
    if isinstance(task.status, Blocked):
        return f"blocked: {one_line(task.status.reason, _TEXT_LIMIT)}", Role.BLOCKED
    if isinstance(task.status, Done):
        return None
    bucket = bucket_of(task, now)
    if bucket is Bucket.OVERDUE:
        return _late_text(task, now), Role.LATE
    if bucket is Bucket.TODAY:
        return _today_text(task, now), Role.DIM
    if bucket is Bucket.UPCOMING and task.due is not None:
        return format_due(task.due, now), Role.DIM
    return ("in review", Role.REVIEW) if isinstance(task.status, Review) else None


def _symbol_role(kind: StatusKind) -> Role:
    match kind:
        case StatusKind.TODO:
            return Role.DIM
        case StatusKind.IN_PROGRESS:
            return Role.RUNNING
        case StatusKind.BLOCKED:
            return Role.BLOCKED
        case StatusKind.REVIEW:
            return Role.REVIEW
        case StatusKind.DONE:
            return Role.OK


def task_line(task: Task, now: datetime, width: int) -> StyledLine:
    """Return `  {symbol} {marker:<2} {title}  @project` with the due text on the right.

    The line is exactly `width` columns: the title is cut with `…` before the due text.
    """
    kind = status_kind(task.status)
    marker = task.priority.marker
    marker_role = Role.HIGH if marker == "!!" else Role.WARN
    if task.project is None:
        where = Span("  (floating)", Role.DIM)
    else:
        where = Span(f"  @{one_line(task.project.name, _NAME_LIMIT)}", Role.KIND)
    left: StyledLine = (
        Span(f"  {kind.symbol}", _symbol_role(kind)),
        Span(" "),
        Span(f"{marker:<2}", marker_role),
        Span(" "),
        Span(one_line(task.title, _TEXT_LIMIT)),
        where,
    )
    short = due_short(task, now)
    right: StyledLine = () if short is None else (Span(short[0], short[1]),)
    return fit(left, right, width)
