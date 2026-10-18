"""Creating, finding and updating sessions."""

import sqlite3
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.rows import as_integer, fetch_all, fetch_one
from meute.core.errors import InvalidInput, NotFound
from meute.core.instants import from_db, to_db
from meute.core.project import ProjectId, RepoId
from meute.core.session import AgentKind, NewSession, Session, SessionId
from meute.core.session_state import Exited, SessionState, is_live, state_from_parts, state_id
from meute.core.task import TaskId

_SELECT = (
    "SELECT id, agent, title, project_id, repo_id, task_id, cwd, state, exit_code,"
    " last_activity_at, created_at, ended_at FROM sessions"
)
_MIN_PREFIX = 4


def _text(value: object) -> str:
    if not isinstance(value, str):
        message = f"corrupt row: expected text, got {value!r}"
        raise ValueError(message)  # noqa: TRY004 — a corrupt database, not a caller error
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else as_integer(value)


def _row_to_session(row: tuple[object, ...]) -> Session:
    project_id, repo_id, task_id = (_optional_integer(row[i]) for i in (3, 4, 5))
    return Session(
        id=SessionId(_text(row[0])),
        agent=AgentKind(_text(row[1])),
        title=_text(row[2]),
        project_id=None if project_id is None else ProjectId(project_id),
        repo_id=None if repo_id is None else RepoId(repo_id),
        task_id=None if task_id is None else TaskId(task_id),
        cwd=Path(_text(row[6])),
        state=state_from_parts(_text(row[7]), _optional_integer(row[8])),
        last_activity_at=from_db(_text(row[9])),
        created_at=from_db(_text(row[10])),
        ended_at=None if row[11] is None else from_db(_text(row[11])),
    )


def _exit_code(state: SessionState) -> int | None:
    return state.code if isinstance(state, Exited) else None


def _fetch(conn: sqlite3.Connection, session_id: SessionId) -> Session | None:
    row = fetch_one(conn, f"{_SELECT} WHERE id = ?", (session_id,))
    return None if row is None else _row_to_session(row)


def create_session(db: Database, new: NewSession) -> Session:
    """Insert a session; its creation and last activity are now.

    Raises:
        InvalidInput: the title is empty or the working directory is not valid UTF-8.
        NotFound: the project, repository or task does not exist.
    """
    title = new.title.strip()
    if not title:
        message = "title cannot be empty"
        raise InvalidInput(message)
    try:
        cwd = str(new.cwd)
        cwd.encode("utf-8")
    except UnicodeEncodeError:
        message = f"path is not valid UTF-8: {new.cwd!r}"
        raise InvalidInput(message) from None
    now = to_db(db.now())
    with db.transaction() as conn:
        for entity, ident, exists in (
            ("project", new.project_id, "SELECT 1 FROM projects WHERE id = ?"),
            ("repository", new.repo_id, "SELECT 1 FROM repos WHERE id = ?"),
            ("task", new.task_id, "SELECT 1 FROM tasks WHERE id = ?"),
        ):
            if ident is not None and fetch_one(conn, exists, (ident,)) is None:
                raise NotFound(entity, str(ident))
        conn.execute(
            "INSERT INTO sessions (id, agent, title, project_id, repo_id, task_id, cwd,"
            " state, exit_code, last_activity_at, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new.id,
                new.agent.value,
                title,
                new.project_id,
                new.repo_id,
                new.task_id,
                cwd,
                state_id(new.state),
                _exit_code(new.state),
                now,
                now,
            ),
        )
        return _require(conn, new.id)


def _require(conn: sqlite3.Connection, session_id: SessionId) -> Session:
    session = _fetch(conn, session_id)
    if session is None:
        entity = "session"
        raise NotFound(entity, session_id)
    return session


def get_session(db: Database, session_id: SessionId) -> Session:
    """Return the session `session_id`.

    Raises:
        NotFound: no such session.
    """
    return _require(db.conn, session_id)


def find_session(db: Database, prefix: str) -> Session:
    """Return the session whose identifier is `prefix` or starts with it.

    A prefix needs at least 4 characters and is compared in lower case, without patterns.

    Raises:
        InvalidInput: several sessions match.
        NotFound: no session matches, or the prefix is too short.
    """
    wanted = prefix.lower()
    entity = "session"
    if len(wanted) < _MIN_PREFIX:
        raise NotFound(entity, prefix)
    rows = fetch_all(
        db.conn,
        f"{_SELECT} WHERE substr(id, 1, ?) = ? ORDER BY created_at, id LIMIT 2",
        (len(wanted), wanted),
    )
    if not rows:
        raise NotFound(entity, prefix)
    if len(rows) > 1:
        message = f"ambiguous session id: {prefix}"
        raise InvalidInput(message)
    return _row_to_session(rows[0])


def list_sessions(db: Database, *, include_ended: bool = False) -> list[Session]:
    """Return the sessions ordered by creation then identifier; live ones unless asked."""
    sessions = [
        _row_to_session(row) for row in fetch_all(db.conn, f"{_SELECT} ORDER BY created_at, id")
    ]
    return sessions if include_ended else [s for s in sessions if is_live(s.state)]


def set_session_state(db: Database, session_id: SessionId, state: SessionState) -> Session:
    """Set the state of a session and its last activity to now.

    `ended_at` is set when the session leaves the live states, and kept afterwards.

    Raises:
        NotFound: no such session.
    """
    now = db.now()
    with db.transaction() as conn:
        before = _require(conn, session_id)
        ended_at = now if is_live(before.state) and not is_live(state) else before.ended_at
        conn.execute(
            "UPDATE sessions SET state = ?, exit_code = ?, last_activity_at = ?, ended_at = ?"
            " WHERE id = ?",
            (
                state_id(state),
                _exit_code(state),
                to_db(now),
                None if ended_at is None else to_db(ended_at),
                session_id,
            ),
        )
        return _require(conn, session_id)
