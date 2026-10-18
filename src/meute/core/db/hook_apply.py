"""Recording an interpreted hook: history always, session fields only when it still applies."""

from meute.core.db.connection import Database
from meute.core.db.rows import as_text, fetch_one, optional
from meute.core.db.sessions import get_session, write_state
from meute.core.hooks import HookEffect
from meute.core.instants import to_db
from meute.core.session import SessionId
from meute.core.session_state import PermissionRequested, is_live


def apply_hook(db: Database, session_id: SessionId, event: str, effect: HookEffect) -> bool:
    """Record `effect` of the hook `event` for a session; return whether its state changed.

    The event is always added to the history. The rest is applied only when the session is
    live and the hook comes from the Claude session already known (same `native_id`).

    Raises:
        NotFound: no such session.
    """
    now = db.now()
    with db.transaction() as conn:
        session = get_session(db, session_id)
        conn.execute(
            "INSERT INTO session_events (session_id, event, detail, created_at)"
            " VALUES (?, ?, ?, ?)",
            (session_id, event, effect.history, to_db(now)),
        )
        row = fetch_one(conn, "SELECT native_id FROM sessions WHERE id = ?", (session_id,))
        known = optional(as_text, row[0]) if row else None
        if not is_live(session.state) or (
            effect.native_id is not None and known is not None and effect.native_id != known
        ):
            return False
        changed: dict[str, str | None] = {
            name: value
            for name, value in (
                ("native_id", effect.native_id),
                ("transcript_path", effect.transcript_path),
                ("model", effect.model),
                ("permission_mode", effect.permission_mode),
                ("last_tool", effect.last_tool),
                ("pending_permission", effect.pending_permission),
                ("last_message", effect.last_message),
            )
            if value is not None
        }
        if effect.state is not None and not isinstance(effect.state, PermissionRequested):
            changed["pending_permission"] = None
        assignments = ", ".join(f"{name} = ?" for name in (*changed, "last_activity_at"))
        conn.execute(
            f"UPDATE sessions SET {assignments} WHERE id = ?",  # noqa: S608 — fixed column names
            (*changed.values(), to_db(now), session_id),
        )
        if effect.state is None:
            return False
        write_state(conn, session, effect.state, now)
        return effect.state != session.state
