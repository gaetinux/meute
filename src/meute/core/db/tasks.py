"""Creating and reading tasks."""

from dataclasses import dataclass, field
from datetime import datetime

from meute.core.actor import Actor
from meute.core.db.connection import Database
from meute.core.db.rows import (
    TASK_SELECT,
    EventRecord,
    due_columns,
    fetch_all,
    fetch_task,
    insert_event,
    inserted_id,
    project_must_exist,
    row_to_event,
    row_to_task,
)
from meute.core.errors import InvalidInput
from meute.core.instants import to_db
from meute.core.project import ProjectId
from meute.core.status import StatusKind
from meute.core.task import NewTask, Task, TaskEvent, TaskId


@dataclass(frozen=True, slots=True, kw_only=True)
class AnyProject:
    """Tasks of every project, and tasks without a project."""


@dataclass(frozen=True, slots=True, kw_only=True)
class InProject:
    """Tasks of one project."""

    project_id: ProjectId


@dataclass(frozen=True, slots=True, kw_only=True)
class Floating:
    """Tasks without a project."""


ProjectFilter = AnyProject | InProject | Floating


@dataclass(frozen=True, slots=True, kw_only=True)
class TaskFilter:
    """Which tasks to list; asking for the `DONE` status implies finished tasks.

    Without `include_done`, the tasks finished at or after `done_since` are listed too.
    """

    include_done: bool = False
    project: ProjectFilter = field(default_factory=AnyProject)
    status: StatusKind | None = None
    done_since: datetime | None = None


def create_task(db: Database, new: NewTask, actor: Actor) -> Task:
    """Create a todo task and record its `created` event.

    Raises:
        InvalidInput: the title is empty.
        NotFound: the project does not exist.
    """
    title = new.title.strip()
    if not title:
        message = "title cannot be empty"
        raise InvalidInput(message)
    now = db.now()
    due_date, due_at = due_columns(new.due)
    with project_must_exist(new.project_id), db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (title, description, status, priority, due_date, due_at,"
            " project_id, version, created_at, updated_at)"
            " VALUES (?, ?, 'todo', ?, ?, ?, ?, 1, ?, ?)",
            (
                title,
                new.description,
                new.priority.value,
                due_date,
                due_at,
                new.project_id,
                to_db(now),
                to_db(now),
            ),
        )
        task_id = TaskId(inserted_id(cursor))
        insert_event(
            conn,
            EventRecord(
                task_id=task_id,
                field="created",
                old_value=None,
                new_value=title,
                actor=actor,
                at=now,
            ),
        )
        return fetch_task(conn, task_id)


def get_task(db: Database, task_id: TaskId) -> Task:
    """Return the task `task_id`.

    Raises:
        NotFound: no such task.
    """
    return fetch_task(db.conn, task_id)


def list_tasks(db: Database, task_filter: TaskFilter) -> list[Task]:
    """Return the tasks matching `task_filter`, by increasing id."""
    clauses: list[str] = []
    params: list[object] = []
    if task_filter.status is not None:
        clauses.append("t.status = ?")
        params.append(task_filter.status.value)
    if not task_filter.include_done and task_filter.status is not StatusKind.DONE:
        if task_filter.done_since is None:
            clauses.append("t.status != 'done'")
        else:
            clauses.append("(t.status != 'done' OR t.completed_at >= ?)")
            params.append(to_db(task_filter.done_since))
    match task_filter.project:
        case AnyProject():
            pass
        case InProject():
            clauses.append("t.project_id = ?")
            params.append(task_filter.project.project_id)
        case Floating():
            clauses.append("t.project_id IS NULL")
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = fetch_all(db.conn, f"{TASK_SELECT}{where} ORDER BY t.id", params)
    return [row_to_task(row) for row in rows]


def history(db: Database, task_id: TaskId) -> list[TaskEvent]:
    """Return the events of the task `task_id`, oldest first."""
    rows = fetch_all(
        db.conn,
        "SELECT task_id, field, old_value, new_value, author, channel, session_id, created_at"
        " FROM task_events WHERE task_id = ? ORDER BY id",
        (task_id,),
    )
    return [row_to_event(row) for row in rows]
