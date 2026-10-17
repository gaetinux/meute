"""Notes attached to tasks."""

from meute.core.actor import Actor
from meute.core.db.connection import Database
from meute.core.db.rows import fetch_all, fetch_task, inserted_id, row_to_note
from meute.core.errors import InvalidInput
from meute.core.instants import to_db
from meute.core.task import Note, TaskId

_NOTE_SELECT = "SELECT id, task_id, body, author, channel, session_id, created_at FROM task_notes"


def add_note(db: Database, task_id: TaskId, body: str, actor: Actor) -> Note:
    """Attach a note to a task; the task version does not change.

    Raises:
        InvalidInput: the body is empty.
        NotFound: no such task.
    """
    cleaned = body.strip()
    if not cleaned:
        message = "note cannot be empty"
        raise InvalidInput(message)
    now = db.now()
    with db.transaction() as conn:
        fetch_task(conn, task_id)
        cursor = conn.execute(
            "INSERT INTO task_notes (task_id, body, author, channel, session_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                task_id,
                cleaned,
                actor.author.value,
                actor.channel.value,
                actor.session_id,
                to_db(now),
            ),
        )
    return Note(
        id=inserted_id(cursor),
        task_id=task_id,
        body=cleaned,
        author=actor.author,
        channel=actor.channel,
        session_id=actor.session_id,
        created_at=now,
    )


def notes(db: Database, task_id: TaskId) -> list[Note]:
    """Return the notes of a task, oldest first."""
    rows = fetch_all(db.conn, f"{_NOTE_SELECT} WHERE task_id = ? ORDER BY id", (task_id,))
    return [row_to_note(row) for row in rows]
