"""Inputs of the MCP task tools, and the JSON forms of a task and its notes."""

import re
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from enum import Enum

from meute.core.errors import InvalidInput
from meute.core.instants import format_instant
from meute.core.json_types import JsonObject
from meute.core.status import (
    Blocked,
    Priority,
    StatusKind,
    TaskStatus,
    parse_status_kind,
    status_from_kind,
    status_kind,
)
from meute.core.status import (
    parse_priority as _parse_priority,
)
from meute.core.task import Due, DueAt, DueDate, Note, Task, due_text

MCP_SERVER_NAME = "meute"
"""The name of meute's MCP server: its key in `mcp.json` and the `mcp__meute__` tool prefix."""

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_WEEK = timedelta(days=7)


class DueFilter(Enum):
    """Which due dates `task_list` keeps."""

    OVERDUE = "overdue"
    TODAY = "today"
    WEEK = "week"


def parse_status(text: str, reason: str | None) -> TaskStatus:
    """Read a status name and its optional reason.

    Raises:
        InvalidInput: the name is unknown, `blocked` has no reason, or another
            status has one.
    """
    kind = parse_status_kind(text)
    if kind is StatusKind.BLOCKED:
        if reason is None or not reason.strip():
            message = "blocked needs a reason"
            raise InvalidInput(message)
    elif reason is not None:
        message = "a reason only goes with blocked"
        raise InvalidInput(message)
    return status_from_kind(kind, reason)


def parse_priority(text: str) -> Priority:
    """Read a priority name.

    Raises:
        InvalidInput: the name is unknown.
    """
    return _parse_priority(text)


def parse_due(text: str) -> Due:
    """Read a due: `YYYY-MM-DD`, or an ISO instant with a time zone.

    Raises:
        InvalidInput: the text is neither.
    """
    try:
        if _ISO_DATE.fullmatch(text):
            return DueDate(day=date.fromisoformat(text))
        at = datetime.fromisoformat(text)
        if at.tzinfo is not None:
            return DueAt(at=at)
    except ValueError:
        pass
    message = f"due must be a date (YYYY-MM-DD) or an instant with a time zone: {text}"
    raise InvalidInput(message)


def parse_due_filter(text: str) -> DueFilter:
    """Read a due filter name.

    Raises:
        InvalidInput: the name is unknown.
    """
    try:
        return DueFilter(text)
    except ValueError:
        message = f"unknown due filter: {text}"
        raise InvalidInput(message) from None


def due_matches(due: Due | None, due_filter: DueFilter, now: datetime) -> bool:
    """Return whether `due` passes `due_filter`, days being read in the zone of `now`.

    `overdue` is strictly before now (a date is late from the next day);
    `today` is the local date of now; `week` is not late and before now plus
    7 days (a date: before the date 7 days from today). A task without a due
    matches nothing.
    """
    match due:
        case None:
            return False
        case DueDate(day=day):
            return _day_matches(day, due_filter, now.date())
        case DueAt(at=at):
            return _instant_matches(at, due_filter, now)


def _day_matches(day: date, due_filter: DueFilter, today: date) -> bool:
    match due_filter:
        case DueFilter.OVERDUE:
            return day < today
        case DueFilter.TODAY:
            return day == today
        case DueFilter.WEEK:
            return today <= day < today + _WEEK


def _instant_matches(at: datetime, due_filter: DueFilter, now: datetime) -> bool:
    match due_filter:
        case DueFilter.OVERDUE:
            return at < now
        case DueFilter.TODAY:
            return at.astimezone(now.tzinfo).date() == now.date()
        case DueFilter.WEEK:
            return now <= at < now + _WEEK


def _project_name(task: Task) -> str | None:
    return None if task.project is None else task.project.name


def task_summary_json(task: Task) -> JsonObject:
    """Return the line of `task_list` for `task`."""
    return {
        "id": task.id,
        "title": task.title,
        "status": status_kind(task.status).value,
        "priority": task.priority.value,
        "due": None if task.due is None else due_text(task.due),
        "project": _project_name(task),
    }


def _note_json(note: Note) -> JsonObject:
    return {
        "id": note.id,
        "body": note.body,
        "author": note.author.value,
        "channel": note.channel.value,
        "session_id": note.session_id,
        "created_at": format_instant(note.created_at),
    }


def task_json(task: Task, notes: Sequence[Note]) -> JsonObject:
    """Return the answer of `task_read`: the whole task and its notes."""
    return {
        **task_summary_json(task),
        "description": task.description,
        "blocked_reason": task.status.reason if isinstance(task.status, Blocked) else None,
        "version": task.version,
        "created_at": format_instant(task.created_at),
        "updated_at": format_instant(task.updated_at),
        "completed_at": None if task.completed_at is None else format_instant(task.completed_at),
        "notes": [_note_json(note) for note in notes],
    }
