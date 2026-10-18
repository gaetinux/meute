"""Reading the Claude columns, the event history and purging old samples."""

from datetime import datetime

from meute.core.claude_session import ClaudeDetails, SessionEvent
from meute.core.db.connection import Database
from meute.core.db.rows import as_instant, as_text, fetch_all, fetch_one, optional
from meute.core.errors import NotFound
from meute.core.instants import to_db
from meute.core.session import SessionId


def get_claude_details(db: Database, session_id: SessionId) -> ClaudeDetails:
    """Return the Claude columns of the session `session_id`.

    Raises:
        NotFound: no such session.
    """
    row = fetch_one(
        db.conn,
        "SELECT native_id, transcript_path, model, permission_mode, last_tool,"
        " pending_permission, last_message FROM sessions WHERE id = ?",
        (session_id,),
    )
    if row is None:
        entity = "session"
        raise NotFound(entity, session_id)
    native_id, transcript_path, model, permission_mode, last_tool, pending, message = (
        optional(as_text, value) for value in row
    )
    return ClaudeDetails(
        native_id=native_id,
        transcript_path=transcript_path,
        model=model,
        permission_mode=permission_mode,
        last_tool=last_tool,
        pending_permission=pending,
        last_message=message,
    )


def session_events(db: Database, session_id: SessionId, *, limit: int = 50) -> list[SessionEvent]:
    """Return the latest `limit` events of a session, the most recent last."""
    rows = fetch_all(
        db.conn,
        "SELECT event, detail, created_at FROM ("
        " SELECT event, detail, created_at, id FROM session_events WHERE session_id = ?"
        " ORDER BY created_at DESC, id DESC LIMIT ?) ORDER BY created_at, id",
        (session_id, limit),
    )
    return [
        SessionEvent(
            session_id=session_id,
            event=as_text(row[0]),
            detail=as_text(row[1]),
            created_at=as_instant(row[2]),
        )
        for row in rows
    ]


def purge_samples(db: Database, *, older_than: datetime) -> int:
    """Delete the metric and quota samples created before `older_than`; return how many."""
    cutoff = to_db(older_than)
    with db.transaction() as conn:
        metrics = conn.execute("DELETE FROM metric_samples WHERE created_at < ?", (cutoff,))
        quotas = conn.execute("DELETE FROM quota_samples WHERE created_at < ?", (cutoff,))
        return metrics.rowcount + quotas.rowcount
