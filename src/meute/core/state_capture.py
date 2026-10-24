"""Capturing the board's live sessions as the entries of a saved state."""

from collections.abc import Sequence

from meute.core.board_sessions import board_session_order
from meute.core.board_view import BoardData
from meute.core.saved_state import SavedSession
from meute.core.session import SessionId
from meute.core.session_state import is_live


def capture(data: BoardData, order: Sequence[SessionId]) -> tuple[SavedSession, ...]:
    """Return the live sessions of `data.sessions` in the order of `order`, as saved entries.

    An id of `order` that `data.sessions` lacks, or whose session has ended, is skipped. The
    conversation id comes from `data.details`; a session without details has none.
    """
    rows = {row.session.id: row for row in data.sessions}
    captured: list[SavedSession] = []
    for session_id in order:
        row = rows.get(session_id)
        if row is None or not is_live(row.session.state):
            continue
        session = row.session
        details = data.details.get(session_id)
        captured.append(
            SavedSession(
                session_id=session_id,
                agent=session.agent,
                cwd=session.cwd,
                native_id=None if details is None else details.native_id,
                title=session.title,
                task_id=session.task_id,
                repo_id=session.repo_id,
                displayed=row.displayed,
            )
        )
    return tuple(captured)


def capture_board(data: BoardData) -> tuple[SavedSession, ...]:
    """Return the live sessions of `data` as saved entries, in the order the board lists them."""
    return capture(data, board_session_order(data))
