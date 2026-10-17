"""Versioned task updates and deletion (optimistic concurrency)."""

from dataclasses import dataclass, replace

from meute.core.actor import Actor
from meute.core.db.connection import Database
from meute.core.db.rows import (
    EventRecord,
    due_columns,
    fetch_task,
    insert_event,
    project_must_exist,
)
from meute.core.errors import InvalidInput, VersionConflict
from meute.core.instants import to_db
from meute.core.project import ProjectId
from meute.core.status import Blocked, Done, Priority, TaskStatus, status_kind, status_text
from meute.core.task import (
    Due,
    Keep,
    Task,
    TaskId,
    TaskPatch,
    due_text,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Fields:
    """The patchable fields of a task."""

    title: str
    description: str
    status: TaskStatus
    priority: Priority
    due: Due | None
    project_id: ProjectId | None


def _fields_of(task: Task) -> _Fields:
    return _Fields(
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due=task.due,
        project_id=None if task.project is None else task.project.id,
    )


def _kept[T](patched: T | Keep, current: T) -> T:
    return current if isinstance(patched, Keep) else patched


def _apply_patch(task: Task, patch: TaskPatch) -> _Fields:
    """Return the fields of `task` after `patch`, whose title is already cleaned."""
    current = _fields_of(task)
    return _Fields(
        title=_kept(patch.title, current.title),
        description=_kept(patch.description, current.description),
        status=_kept(patch.status, current.status),
        priority=_kept(patch.priority, current.priority),
        due=_kept(patch.due, current.due),
        project_id=_kept(patch.project_id, current.project_id),
    )


def _event_values(task: Task) -> list[tuple[str, str | None]]:
    """Return `(field, text)` for each field in event order."""
    return [
        ("title", task.title),
        ("description", task.description),
        ("status", status_text(task.status)),
        ("priority", task.priority.value),
        ("due", None if task.due is None else due_text(task.due)),
        ("project", None if task.project is None else task.project.name),
    ]


def diff_tasks(old: Task, new: Task) -> list[tuple[str, str | None, str | None]]:
    """Return `(field, old_text, new_text)` for each field that differs, in event order."""
    return [
        (name, before, after)
        for (name, before), (_, after) in zip(_event_values(old), _event_values(new), strict=True)
        if before != after
    ]


def _completed_at(current: Task, status: TaskStatus, now_text: str) -> str | None:
    if not isinstance(status, Done):
        return None
    if current.completed_at is not None:
        return to_db(current.completed_at)
    return now_text


def update_task(
    db: Database, task_id: TaskId, expected_version: int, patch: TaskPatch, actor: Actor
) -> Task:
    """Apply `patch` to a task if it is still at `expected_version`.

    A patch that changes nothing returns the task untouched, without a new version.

    Raises:
        InvalidInput: the new title is empty.
        NotFound: no such task, or the patch names an unknown project.
        VersionConflict: the task is no longer at `expected_version`.
    """
    if isinstance(patch.title, str):
        cleaned = patch.title.strip()
        if not cleaned:
            message = "title cannot be empty"
            raise InvalidInput(message)
        patch = replace(patch, title=cleaned)
    now = db.now()
    now_text = to_db(now)
    with db.transaction() as conn:
        current = fetch_task(conn, task_id)
        if current.version != expected_version:
            raise VersionConflict(current)
        wanted = _apply_patch(current, patch)
        if wanted == _fields_of(current):
            return current
        due_date, due_at = due_columns(wanted.due)
        with project_must_exist(wanted.project_id):
            cursor = conn.execute(
                "UPDATE tasks SET title = ?, description = ?, status = ?, blocked_reason = ?,"
                " priority = ?, due_date = ?, due_at = ?, project_id = ?, completed_at = ?,"
                " version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                (
                    wanted.title,
                    wanted.description,
                    status_kind(wanted.status).value,
                    wanted.status.reason if isinstance(wanted.status, Blocked) else None,
                    wanted.priority.value,
                    due_date,
                    due_at,
                    wanted.project_id,
                    _completed_at(current, wanted.status, now_text),
                    now_text,
                    task_id,
                    expected_version,
                ),
            )
        if cursor.rowcount == 0:  # defensive: BEGIN IMMEDIATE already excludes concurrent writers
            raise VersionConflict(fetch_task(conn, task_id))
        updated = fetch_task(conn, task_id)
        for name, before, after in diff_tasks(current, updated):
            insert_event(
                conn,
                EventRecord(
                    task_id=task_id,
                    field=name,
                    old_value=before,
                    new_value=after,
                    actor=actor,
                    at=now,
                ),
            )
        return updated


def delete_task(db: Database, task_id: TaskId, expected_version: int, actor: Actor) -> None:
    """Delete a task still at `expected_version`, keeping its history.

    Raises:
        NotFound: no such task.
        VersionConflict: the task is no longer at `expected_version`.
    """
    with db.transaction() as conn:
        current = fetch_task(conn, task_id)
        if current.version != expected_version:
            raise VersionConflict(current)
        insert_event(
            conn,
            EventRecord(
                task_id=task_id,
                field="deleted",
                old_value=current.title,
                new_value=None,
                actor=actor,
                at=db.now(),
            ),
        )
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
