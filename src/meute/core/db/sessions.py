"""Creating, finding and updating sessions."""

import sqlite3
from datetime import datetime
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.rows import (
    as_instant,
    as_integer,
    as_text,
    fetch_all,
    fetch_one,
    optional,
)
from meute.core.errors import InvalidInput, NotFound
from meute.core.instants import to_db
from meute.core.project import ProjectId, RepoId
from meute.core.session import AgentKind, NewSession, Session, SessionId
from meute.core.session_state import (
    Exited,
    SessionState,
    Unknown,
    is_live,
    state_from_parts,
    state_id,
)
from meute.core.task import TaskId

_SELECT = (
    "SELECT id, agent, title, project_id, repo_id, task_id, cwd, state, exit_code,"
    " last_activity_at, created_at, ended_at FROM sessions"
)
_MIN_PREFIX = 4
_ENDED_STATES = "('exited', 'unreachable')"  # the states `is_live` rejects


_text = as_text


def _row_to_session(row: tuple[object, ...]) -> Session:
    project_id, repo_id, task_id = (optional(as_integer, row[i]) for i in (3, 4, 5))
    return Session(
        id=SessionId(_text(row[0])),
        agent=AgentKind(_text(row[1])),
        title=_text(row[2]),
        project_id=None if project_id is None else ProjectId(project_id),
        repo_id=None if repo_id is None else RepoId(repo_id),
        task_id=None if task_id is None else TaskId(task_id),
        cwd=Path(_text(row[6])),
        state=state_from_parts(_text(row[7]), optional(as_integer, row[8])),
        last_activity_at=as_instant(row[9]),
        created_at=as_instant(row[10]),
        ended_at=optional(as_instant, row[11]),
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
            " state, exit_code, last_activity_at, created_at, permission_mode)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                new.permission_mode,
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
    where = "" if include_ended else f" WHERE state NOT IN {_ENDED_STATES}"
    rows = fetch_all(db.conn, f"{_SELECT}{where} ORDER BY created_at, id")
    return [_row_to_session(row) for row in rows]


def last_agent_by_repo(db: Database) -> dict[RepoId, AgentKind]:
    """Return, for each repository, the type of its most recent session (ended ones too).

    The most recent is the greatest `(created_at, id)`; sessions without a repository are
    ignored.
    """
    rows = fetch_all(
        db.conn,
        "SELECT repo_id, agent FROM (SELECT repo_id, agent, ROW_NUMBER() OVER ("
        " PARTITION BY repo_id ORDER BY created_at DESC, id DESC) AS rn"
        " FROM sessions WHERE repo_id IS NOT NULL) WHERE rn = 1",
    )
    return {RepoId(as_integer(row[0])): AgentKind(as_text(row[1])) for row in rows}


def set_session_state(db: Database, session_id: SessionId, state: SessionState) -> Session:
    """Set the state of a session and its last activity to now.

    `ended_at` is set when the session leaves the live states, and kept afterwards.

    Raises:
        NotFound: no such session.
    """
    with db.transaction() as conn:
        write_state(conn, _require(conn, session_id), state, db.now())
        return _require(conn, session_id)


def reopen_session(db: Database, session_id: SessionId) -> Session:
    """Make an ended session live again: unknown state, exit code and end time cleared.

    The last activity is now. Nothing else changes.

    Raises:
        InvalidInput: the session is still live; nothing was written.
        NotFound: no such session.
    """
    with db.transaction() as conn:
        session = _require(conn, session_id)
        if is_live(session.state):
            message = f'"{session.title}" is still running'
            raise InvalidInput(message)
        conn.execute(
            "UPDATE sessions SET state = ?, exit_code = NULL, ended_at = NULL,"
            " last_activity_at = ? WHERE id = ?",
            (state_id(Unknown()), to_db(db.now()), session_id),
        )
        return _require(conn, session_id)


def write_state(
    conn: sqlite3.Connection, before: Session, state: SessionState, now: datetime
) -> None:
    """Write `state` for the session `before` inside the caller's transaction.

    Sets the last activity to `now`, and `ended_at` when the session leaves the live states.
    """
    ended_at = now if is_live(before.state) and not is_live(state) else before.ended_at
    conn.execute(
        "UPDATE sessions SET state = ?, exit_code = ?, last_activity_at = ?, ended_at = ?"
        " WHERE id = ?",
        (
            state_id(state),
            _exit_code(state),
            to_db(now),
            None if ended_at is None else to_db(ended_at),
            before.id,
        ),
    )


def set_assumed_state(db: Database, judged: Session, state: SessionState) -> bool:
    """Record an assumed `state` unless the session changed since it was read as `judged`.

    Meant for states guessed from silence or `claude agents`: a hook that landed in between
    wins, and the last activity is kept, since nothing was heard from the session.
    Returns whether the row was written.
    """
    with db.transaction() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET state = ?, exit_code = ? WHERE id = ? AND state = ?"
            " AND exit_code IS ? AND last_activity_at = ?",
            (
                state_id(state),
                _exit_code(state),
                judged.id,
                state_id(judged.state),
                _exit_code(judged.state),
                to_db(judged.last_activity_at),
            ),
        )
        return cursor.rowcount == 1
