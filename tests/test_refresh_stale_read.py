"""An assumed state judged from a stale read never overwrites a concurrent hook (principle 5)."""

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from meute.cli.session_refresh import AgentsReading, apply_refresh
from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.db.sessions import create_session, get_session, list_sessions, set_assumed_state
from meute.core.hooks import HookEffect
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Idle, MaybeStuck, Running
from meute.tmux.parse import PaneId, PaneInfo
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
LATER = FIXED + timedelta(minutes=30)
STUCK = timedelta(minutes=10)


def _pane() -> PaneInfo:
    return PaneInfo(
        id=PaneId("%1"), session="s", window="w", meute_id=SID, role=None,
        dead=False, dead_status=None, width=80,
    )  # fmt: skip


def _make(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Running()),
    )


def test_hook_between_read_and_assumed_write_wins(db: Database) -> None:
    _make(db)
    stale = list_sessions(db, include_ended=True)  # refresh reads the sessions first
    _ = apply_hook(db, SID, "SessionEnd", HookEffect(state=Exited(code=None), history="exit"))
    ended = get_session(db, SID)
    reading = AgentsReading(agents=(), now=LATER, stuck_after=STUCK)
    _ = apply_refresh(replace(db, clock=lambda: LATER), [_pane()], sessions=stale, reading=reading)
    after = get_session(db, SID)
    assert after.state == Exited(code=None)
    assert after.ended_at == ended.ended_at
    assert after.last_activity_at == ended.last_activity_at


def test_assumed_state_keeps_last_activity(db: Database) -> None:
    _make(db)
    before = get_session(db, SID)
    reading = AgentsReading(agents=(), now=LATER, stuck_after=STUCK)
    _ = apply_refresh(replace(db, clock=lambda: LATER), [_pane()], reading=reading)
    after = get_session(db, SID)
    assert after.state == MaybeStuck()
    assert after.last_activity_at == before.last_activity_at


def test_set_assumed_state_writes_only_an_unchanged_row(db: Database) -> None:
    _make(db)
    judged = get_session(db, SID)
    assert set_assumed_state(db, judged, Idle())
    assert get_session(db, SID).state == Idle()
    assert not set_assumed_state(db, judged, MaybeStuck())  # the row moved on since `judged`
    assert get_session(db, SID).state == Idle()
