"""Assumed states and the sessions outside meute."""

from datetime import timedelta
from pathlib import Path

import pytest

from meute.core.agents import AgentInfo, assumed_state, outside_agents
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import (
    Exited,
    Idle,
    MaybeStuck,
    PermissionRequested,
    Running,
    SessionState,
    SubagentRunning,
    Unreachable,
    WaitingInput,
)
from support import FIXED

STUCK = timedelta(minutes=10)
NOW = FIXED + timedelta(minutes=30)
SID = SessionId("aaaa1111-0000-4000-8000-000000000000")


def _session(
    state: SessionState,
    *,
    agent: AgentKind = AgentKind.CLAUDE,
    sid: SessionId = SID,
    silent: timedelta = timedelta(minutes=30),
) -> Session:
    return Session(
        id=sid,
        agent=agent,
        title="t",
        project_id=None,
        repo_id=None,
        task_id=None,
        cwd=Path("/w"),
        state=state,
        last_activity_at=NOW - silent,
        created_at=FIXED,
        ended_at=None,
    )


def _agent(status: str, session_id: str = SID) -> AgentInfo:
    return AgentInfo(
        pid=1, cwd="/w", kind="interactive", session_id=session_id, name="n", status=status
    )


def _assume(session: Session, agent: AgentInfo | None) -> SessionState | None:
    return assumed_state(session, agent, now=NOW, stuck_after=STUCK)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("busy", Running()), ("waiting", WaitingInput()), ("idle", Idle())],
)
def test_official_status_wins_after_silence(status: str, expected: SessionState) -> None:
    assert _assume(_session(PermissionRequested()), _agent(status)) == expected


def test_same_state_means_no_change() -> None:
    assert _assume(_session(Idle()), _agent("idle")) is None


def test_unknown_status_changes_nothing() -> None:
    assert _assume(_session(Running()), _agent("weird")) is None


def test_recent_activity_changes_nothing() -> None:
    recent = _session(Running(), silent=timedelta(minutes=9))
    assert _assume(recent, None) is None
    assert _assume(recent, _agent("idle")) is None


def test_exactly_the_threshold_is_not_yet_stuck() -> None:
    assert _assume(_session(Running(), silent=STUCK), None) is None


@pytest.mark.parametrize("state", [Running(), SubagentRunning()])
def test_silent_running_without_agent_is_maybe_stuck(state: SessionState) -> None:
    assert _assume(_session(state), None) == MaybeStuck()


@pytest.mark.parametrize("state", [WaitingInput(), Idle(), MaybeStuck(), PermissionRequested()])
def test_other_states_without_agent_stay(state: SessionState) -> None:
    assert _assume(_session(state), None) is None


def test_bash_session_is_never_assumed() -> None:
    bash = _session(Running(), agent=AgentKind.BASH)
    assert _assume(bash, None) is None
    assert _assume(bash, _agent("idle")) is None


@pytest.mark.parametrize("state", [Exited(code=0), Unreachable()])
def test_ended_session_is_never_assumed(state: SessionState) -> None:
    assert _assume(_session(state), None) is None
    assert _assume(_session(state), _agent("busy")) is None


def test_outside_agents_exclude_meute_sessions() -> None:
    other = SessionId("bbbb2222-0000-4000-8000-000000000000")
    sessions = [_session(Running(), sid=SID), _session(Running(), sid=other)]
    agents = (_agent("idle", SID), _agent("idle", "native-1"), _agent("busy", "stranger"))
    assert outside_agents(agents, sessions, native_ids=["native-1"]) == (agents[2],)
    assert outside_agents(agents, sessions) == (agents[1], agents[2])
