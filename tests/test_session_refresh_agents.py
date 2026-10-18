"""`apply_refresh` with `claude agents --json` knowledge."""

from datetime import timedelta
from pathlib import Path

from meute.cli.session_refresh import AgentsReading, apply_refresh
from meute.core.agents import AgentInfo
from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, get_session
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Idle, MaybeStuck, Running
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


def _agent(session_id: str, status: str = "idle") -> AgentInfo:
    return AgentInfo(pid=1, cwd="/w", kind="i", session_id=session_id, name="n", status=status)


def _apply(db: Database, agents: tuple[AgentInfo, ...] | None):  # noqa: ANN202 — test helper
    reading = None if agents is None else AgentsReading(agents=agents, now=LATER, stuck_after=STUCK)
    return apply_refresh(db, [_pane()], reading=reading)


def test_not_consulting_changes_nothing(db: Database) -> None:
    _make(db)
    _ = _apply(db, None)
    assert get_session(db, SID).state == Running()


def test_silent_session_without_agent_becomes_stuck(db: Database) -> None:
    _make(db)
    snapshot = _apply(db, ())
    assert get_session(db, SID).state == MaybeStuck()
    assert snapshot.sessions[0].session.state == MaybeStuck()


def test_official_status_is_applied_by_id(db: Database) -> None:
    _make(db)
    _ = _apply(db, (_agent(SID, "idle"),))
    assert get_session(db, SID).state == Idle()


def test_outside_excludes_known_sessions(db: Database) -> None:
    _make(db)
    stranger = _agent("zzz")
    snapshot = _apply(db, (_agent(SID), stranger))
    assert snapshot.outside == (stranger,)


def test_agent_without_id_never_matches_a_session_without_native_id(db: Database) -> None:
    _make(db)
    nameless = _agent("", "idle")
    snapshot = _apply(db, (nameless,))
    assert get_session(db, SID).state == MaybeStuck()  # not corrected to idle by the nameless agent
    assert snapshot.outside == (nameless,)
