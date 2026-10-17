"""Plain-text rendering of tasks (specification section 9.5)."""

from collections.abc import Sequence
from datetime import datetime

from meute.core.quick_add import QuickAdd
from meute.core.status import Blocked, Done, InProgress, Review, StatusKind, Todo, status_kind
from meute.core.task import Due, Note, Task, task_label
from meute.core.views import format_due, is_overdue

_STAMP = "%Y-%m-%d %H:%M"


def _line(lead: Sequence[str], title: str, project: str | None, tail: str | None) -> str:
    parts = [*lead, title, f"@{project}" if project else ""]
    text = " ".join(part for part in parts if part)
    return f"{text} · {tail}" if tail else text


def task_line(task: Task, now: datetime) -> str:
    """Render `#12 » ! Title @project · tail`."""
    tail: str | None
    match task.status:
        case Blocked(reason=reason):
            tail = f"blocked: {reason}"
        case Review():
            tail = "in review"
        case Todo() | InProgress() | Done():
            tail = None if task.due is None else format_due(task.due, now)
            if tail and is_overdue(task, now):
                tail += " (overdue)"
    lead = (task_label(task.id), status_kind(task.status).symbol, task.priority.marker)
    return _line(lead, task.title, task.project.name if task.project else None, tail)


def preview_line(parsed: QuickAdd, now: datetime) -> str:
    """Render what a quick entry would create: the task line without identifier."""
    due: Due | None = parsed.due
    lead = (StatusKind.TODO.symbol, parsed.priority.marker)
    return _line(lead, parsed.title, parsed.project, None if due is None else format_due(due, now))


def _stamp(moment: datetime, now: datetime) -> str:
    return moment.astimezone(now.tzinfo).strftime(_STAMP)


def task_detail(task: Task, notes: Sequence[Note], now: datetime) -> str:
    """Render every field of `task`, then its notes."""
    status = status_kind(task.status).label
    if isinstance(task.status, Blocked):
        status += f" ({task.status.reason})"
    lines = [
        f"{task_label(task.id)} {task.title}",
        f"Status: {status}",
        f"Priority: {task.priority.value}",
        f"Due: {'—' if task.due is None else format_due(task.due, now)}",
        f"Project: {task.project.name if task.project else '—'}",
        f"Version: {task.version}",
        f"Created: {_stamp(task.created_at, now)}",
        f"Updated: {_stamp(task.updated_at, now)}",
    ]
    if task.completed_at is not None:
        lines.append(f"Completed: {_stamp(task.completed_at, now)}")
    if task.description:
        lines.append(f"Description: {task.description}")
    if notes:
        lines.append("Notes:")
        lines.extend(
            f"[{_stamp(note.created_at, now)}] {note.author.value}: {note.body}" for note in notes
        )
    return "\n".join(lines)
