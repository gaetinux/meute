"""Saved states in the database: saved with retention, listed, read and removed."""

from collections.abc import Sequence

from meute.core.db.connection import Database
from meute.core.db.rows import as_instant, as_text, fetch_all, fetch_one
from meute.core.errors import NotFound
from meute.core.instants import to_db
from meute.core.saved_state import (
    LAST,
    RETAINED,
    SavedSession,
    SavedState,
    parse_sessions,
    sessions_json,
)

_SELECT = "SELECT name, created_at, sessions FROM saved_states"


def _row_to_state(row: tuple[object, ...]) -> SavedState:
    return SavedState(
        name=as_text(row[0]),
        created_at=as_instant(row[1]),
        sessions=parse_sessions(as_text(row[2])),
    )


def _not_found(name: str) -> NotFound:
    return NotFound("saved state", name, message=f"no saved state named {name}")


def save_state(db: Database, name: str, sessions: Sequence[SavedSession]) -> SavedState:
    """Save `sessions` under `name`, replacing a state of that name; it becomes the newest.

    `name` is stored as given (see `state_name` for the names a user types). Unless it is
    `LAST`, the named states beyond the `RETAINED` newest are removed, `LAST` aside, in the
    same transaction.
    """
    with db.transaction() as conn:
        # deleted then inserted: a fresh id orders the states saved at the same instant
        conn.execute("DELETE FROM saved_states WHERE name = ?", (name,))
        row = fetch_one(
            conn,
            "INSERT INTO saved_states (name, created_at, sessions) VALUES (?, ?, ?)"
            " RETURNING name, created_at, sessions",
            (name, to_db(db.now()), sessions_json(sessions)),
        )
        if name != LAST:
            conn.execute(
                "DELETE FROM saved_states WHERE id IN (SELECT id FROM saved_states"
                " WHERE name != ? ORDER BY created_at DESC, id DESC LIMIT -1 OFFSET ?)",
                (LAST, RETAINED),
            )
    if row is None:
        message = "INSERT returned no row"
        raise RuntimeError(message)
    return _row_to_state(row)


def list_states(db: Database) -> tuple[SavedState, ...]:
    """Return every state: `LAST` first, then the others from the newest to the oldest."""
    rows = fetch_all(
        db.conn,
        f"{_SELECT} ORDER BY name = ? DESC, created_at DESC, id DESC",
        (LAST,),
    )
    return tuple(_row_to_state(row) for row in rows)


def get_state(db: Database, name: str) -> SavedState:
    """Return the state called `name`.

    Raises:
        NotFound: no state has that name (`no saved state named <name>`).
    """
    row = fetch_one(db.conn, f"{_SELECT} WHERE name = ?", (name,))
    if row is None:
        raise _not_found(name)
    return _row_to_state(row)


def delete_state(db: Database, name: str) -> None:
    """Remove the state called `name`.

    Raises:
        NotFound: no state has that name (`no saved state named <name>`).
    """
    with db.transaction() as conn:
        removed = conn.execute("DELETE FROM saved_states WHERE name = ?", (name,)).rowcount
    if removed == 0:
        raise _not_found(name)
