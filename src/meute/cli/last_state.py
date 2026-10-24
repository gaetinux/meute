"""Keeping the `last` state up to date with the board's live sessions."""

from dataclasses import replace

from meute.core.board_sessions import board_session_order
from meute.core.board_view import BoardData
from meute.core.db.connection import Database
from meute.core.db.saved_states import get_state, list_states, save_state
from meute.core.errors import NotFound
from meute.core.saved_state import LAST, SavedSession
from meute.core.session import SessionId
from meute.core.state_capture import capture


class LastState:
    """Writes `last` when the ids of the live sessions change, and never an empty list.

    The list last written is read from the database at the first update: a board that
    restarts (after a reboot, every session unreachable) leaves `last` as it was.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._written: tuple[SessionId, ...] | None = None  # None: not read yet

    def update(self, sessions: tuple[SavedSession, ...]) -> bool:
        """Write `sessions` as `last` if their ids changed and there is one; return if written."""
        if self._written is None:
            self._written = self._stored()
        ids = tuple(session.session_id for session in sessions)
        if not ids or ids == self._written:
            return False
        _ = save_state(self._db, LAST, sessions)
        self._written = ids
        return True

    def follow(self, data: BoardData) -> BoardData:
        """Update `last` from the live sessions of `data`, in the board order.

        Returns `data`, with its saved states read again when `last` was written.
        """
        if not self.update(capture(data, board_session_order(data))):
            return data
        return replace(data, saved_states=list_states(self._db))

    def _stored(self) -> tuple[SessionId, ...]:
        try:
            state = get_state(self._db, LAST)
        except NotFound:
            return ()
        return tuple(session.session_id for session in state.sessions)
