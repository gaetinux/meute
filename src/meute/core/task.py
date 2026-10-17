"""The task model and its JSON forms."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import Enum
from typing import NewType

from meute.core.actor import Author, Channel
from meute.core.errors import InvalidInput
from meute.core.instants import format_instant
from meute.core.json_types import JsonObject
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.status import Blocked, Priority, TaskStatus, status_kind

TaskId = NewType("TaskId", int)


def task_label(task_id: TaskId) -> str:
    """Return the display label of a task, e.g. `#12`."""
    return f"#{task_id}"


@dataclass(frozen=True, slots=True, kw_only=True)
class DueDate:
    """A due date without a time."""

    day: date


@dataclass(frozen=True, slots=True, kw_only=True)
class DueAt:
    """A due instant, stored in UTC."""

    at: datetime

    def __post_init__(self) -> None:
        """Normalise to UTC.

        Raises:
            ValueError: `at` is naive.
        """
        if self.at.tzinfo is None:
            message = "a due instant cannot be a naive datetime"
            raise ValueError(message)
        object.__setattr__(self, "at", self.at.astimezone(UTC))


Due = DueDate | DueAt


def due_text(due: Due) -> str:
    """Return the text of `due`: an ISO date or a UTC instant."""
    match due:
        case DueDate():
            return due.day.isoformat()
        case DueAt():
            return format_instant(due.at)


def due_to_json(due: Due) -> JsonObject:
    """Return the tagged JSON form of `due`."""
    kind = "date" if isinstance(due, DueDate) else "at"
    return {"kind": kind, "value": due_text(due)}


def due_from_json(data: Mapping[str, object]) -> Due:
    """Read a due from its tagged JSON form.

    Raises:
        InvalidInput: the data has another shape.
    """
    kind, value = data.get("kind"), data.get("value")
    try:
        if kind == "date" and isinstance(value, str):
            return DueDate(day=date.fromisoformat(value))
        if kind == "at" and isinstance(value, str):
            return DueAt(at=datetime.fromisoformat(value))
    except ValueError as error:
        message = f"invalid due: {error}"
        raise InvalidInput(message) from error
    message = f"invalid due: {dict(data)}"
    raise InvalidInput(message)


@dataclass(frozen=True, slots=True, kw_only=True)
class Task:
    """A task as stored."""

    id: TaskId
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    due: Due | None
    project: ProjectRef | None
    repo_id: RepoId | None
    version: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewTask:
    """The data needed to create a task."""

    title: str
    description: str = ""
    priority: Priority = Priority.NORMAL
    due: Due | None = None
    project_id: ProjectId | None = None


class Keep(Enum):
    """Marker meaning that a patched field stays unchanged."""

    KEEP = "keep"


KEEP = Keep.KEEP


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskPatch:
    """A partial update: `KEEP` leaves a field unchanged, `None` clears it."""

    title: str | Keep = KEEP
    description: str | Keep = KEEP
    status: TaskStatus | Keep = KEEP
    priority: Priority | Keep = KEEP
    due: Due | Keep | None = KEEP
    project_id: ProjectId | Keep | None = KEEP


@dataclass(frozen=True, slots=True, kw_only=True)
class Note:
    """A note attached to a task."""

    id: int
    task_id: TaskId
    body: str
    author: Author
    channel: Channel
    session_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskEvent:
    """One recorded change of a task field."""

    task_id: TaskId
    field: str
    old_value: str | None
    new_value: str | None
    author: Author
    channel: Channel
    session_id: str | None
    created_at: datetime


def task_to_json(task: Task) -> JsonObject:
    """Return the flat JSON form of `task`."""
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "status": status_kind(task.status).value,
        "blocked_reason": task.status.reason if isinstance(task.status, Blocked) else None,
        "priority": task.priority.value,
        "due": None if task.due is None else due_to_json(task.due),
        "project": None
        if task.project is None
        else {"id": task.project.id, "name": task.project.name},
        "repo_id": task.repo_id,
        "version": task.version,
        "created_at": format_instant(task.created_at),
        "updated_at": format_instant(task.updated_at),
        "completed_at": None if task.completed_at is None else format_instant(task.completed_at),
    }


def note_to_json(note: Note) -> JsonObject:
    """Return the JSON form of `note`."""
    return {
        "id": note.id,
        "task_id": note.task_id,
        "body": note.body,
        "author": note.author.value,
        "channel": note.channel.value,
        "session_id": note.session_id,
        "created_at": format_instant(note.created_at),
    }
