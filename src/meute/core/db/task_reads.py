"""Reads that serve the board: the latest notes of every task, the repositories of a project."""

import json
from collections.abc import Collection

from meute.core.db.connection import Database
from meute.core.db.rows import fetch_all, row_to_note
from meute.core.project import ProjectId, RepoId
from meute.core.task import Note, TaskId

_LATEST_NOTES = (
    "SELECT id, task_id, body, author, channel, session_id, created_at FROM ("
    " SELECT id, task_id, body, author, channel, session_id, created_at,"
    " ROW_NUMBER() OVER (PARTITION BY task_id ORDER BY created_at DESC, id DESC) AS rank"
    " FROM task_notes{where}) WHERE rank <= ? ORDER BY task_id, created_at DESC, id DESC"
)
# The ids travel as one JSON array: a single bound parameter, whatever their number.
_OF_TASKS = " WHERE task_id IN (SELECT value FROM json_each(?))"


def latest_notes(
    db: Database, *, per_task: int = 2, task_ids: Collection[TaskId] | None = None
) -> dict[TaskId, tuple[Note, ...]]:
    """Return the `per_task` newest notes of each task, newest first, in one query.

    Only the tasks of `task_ids` are read when given. Tasks without a note are absent.
    """
    if task_ids is None:
        sql, params = _LATEST_NOTES.format(where=""), (per_task,)
    else:
        ids = json.dumps(sorted(task_ids))
        sql, params = _LATEST_NOTES.format(where=_OF_TASKS), (ids, per_task)
    found: dict[TaskId, list[Note]] = {}
    for row in fetch_all(db.conn, sql, params):
        note = row_to_note(row)
        found.setdefault(note.task_id, []).append(note)
    return {task_id: tuple(notes) for task_id, notes in found.items()}


def project_repo_ids(db: Database, project_id: ProjectId) -> list[RepoId]:
    """Return the ids of the repositories attached to a project, by increasing id."""
    rows = fetch_all(
        db.conn,
        "SELECT repo_id FROM project_repos WHERE project_id = ? ORDER BY repo_id",
        (project_id,),
    )
    return [RepoId(int(str(row[0]))) for row in rows]
