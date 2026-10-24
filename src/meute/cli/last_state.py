"""Keeping the `last` state up to date with the board's live sessions."""

import sqlite3
from collections.abc import Sequence
from dataclasses import replace

from meute.core.board_view import BoardData
from meute.core.db.connection import Database
from meute.core.db.saved_states import list_states, save_state
from meute.core.errors import MeuteError
from meute.core.saved_state import LAST, SavedSession, SavedState
from meute.core.session import SessionId
from meute.core.session_state import is_live
from meute.core.state_capture import capture_board


def _last_ids(states: Sequence[SavedState]) -> set[SessionId]:
    """The ids of the sessions of the `last` of `states`; none without one."""
    stored = next((state for state in states if state.name == LAST), None)
    return {saved.session_id for saved in (() if stored is None else stored.sessions)}


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
        known = _last_ids(states)
        if all(session.session_id in known for session in sessions):
            return False
        _ = save_state(self._db, LAST, sessions)
        return True

    def follow(self, data: BoardData) -> BoardData:
        """Update `last` from the live sessions of `data`, in the board order.

        Returns `data`, with its saved states read again when `last` was written. A write the
        database refuses leaves `data` as read: the next read tries again.
        """
        live = {row.session.id for row in data.sessions if is_live(row.session.state)}
        if live <= _last_ids(data.saved_states):
            return data
        try:
            if not self.update(capture_board(data), data.saved_states):
                return data
        except (MeuteError, sqlite3.Error):
            return data
        return replace(data, saved_states=list_states(self._db))
