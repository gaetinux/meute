"""Keeping the `last` state up to date with the board's live sessions."""

import sqlite3
from collections.abc import Sequence
from dataclasses import replace

from meute.core.board_sessions import board_session_order
from meute.core.board_view import BoardData
from meute.core.db.connection import Database
from meute.core.db.saved_states import list_states, save_state
from meute.core.errors import MeuteError
from meute.core.saved_state import LAST, SavedSession, SavedState
from meute.core.state_capture import capture


class LastState:
    """Writes `last` when a live session is missing from it, and never makes it shrink.

    A stopped session, a new order or no live session at all (a board restarting after a
    reboot) writes nothing: `last` keeps the sessions until a new one starts.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    def update(self, sessions: tuple[SavedSession, ...], states: Sequence[SavedState]) -> bool:
        """Write `sessions` as `last` if one is missing from the `last` of `states`.

        Returns whether `last` was written.
        """
        stored = next((state for state in states if state.name == LAST), None)
        known = {saved.session_id for saved in (() if stored is None else stored.sessions)}
        if all(session.session_id in known for session in sessions):
            return False
        _ = save_state(self._db, LAST, sessions)
        return True

    def follow(self, data: BoardData) -> BoardData:
        """Update `last` from the live sessions of `data`, in the board order.

        Returns `data`, with its saved states read again when `last` was written. A write the
        database refuses leaves `data` as read: the next read tries again.
        """
        sessions = capture(data, board_session_order(data))
        try:
            if not self.update(sessions, data.saved_states):
                return data
        except (MeuteError, sqlite3.Error):
            return data
        return replace(data, saved_states=list_states(self._db))
