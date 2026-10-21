"""Reopening an ended session: back to unknown, ended marks cleared."""

from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.rows import fetch_one
from meute.core.db.sessions import create_session, get_session, reopen_session, set_session_state
from meute.core.errors import InvalidInput, NotFound
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Idle, Unknown, Unreachable
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")


def _claude(db: Database) -> None:
    _ = create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="work", cwd=Path("/w"), state=Unknown()),
    )


@pytest.mark.parametrize("ended", [Exited(code=2), Unreachable()])
def test_an_ended_session_becomes_unknown_again(db: Database, ended: Exited | Unreachable) -> None:
    _claude(db)
    _ = set_session_state(db, SID, ended)
    assert get_session(db, SID).ended_at is not None
    reopened = reopen_session(db, SID)
    assert reopened == get_session(db, SID)
    assert reopened.state == Unknown()
    assert reopened.ended_at is None
    assert reopened.last_activity_at == FIXED
    row = fetch_one(db.conn, "SELECT exit_code FROM sessions WHERE id = ?", (SID,))
    assert row == (None,)


def test_a_live_session_is_refused_and_untouched(db: Database) -> None:
    _claude(db)
    before = set_session_state(db, SID, Idle())
    with pytest.raises(InvalidInput, match=r'^"work" is still running$'):
        _ = reopen_session(db, SID)
    assert get_session(db, SID) == before


def test_an_unknown_session_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound):
        _ = reopen_session(db, SID)
