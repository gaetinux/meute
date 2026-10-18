"""The reconciliation rule between recorded sessions and observed panes."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from meute.core.reconcile import PaneObservation, reconcile
from meute.core.session import AgentKind, Session, SessionId
from meute.core.session_state import (
    Exited,
    Idle,
    Running,
    SessionState,
    Unknown,
    Unreachable,
    is_live,
)
from support import FIXED

A = SessionId("00000000-0000-4000-8000-00000000000a")
B = SessionId("00000000-0000-4000-8000-00000000000b")


def make(session_id: SessionId, state: SessionState, agent: AgentKind = AgentKind.BASH) -> Session:
    return Session(
        id=session_id,
        agent=agent,
        title="t",
        project_id=None,
        repo_id=None,
        task_id=None,
        cwd=Path("/work"),
        state=state,
        last_activity_at=FIXED,
        created_at=FIXED,
        ended_at=None,
    )


def alive(pane_id: str) -> PaneObservation:
    return PaneObservation(meute_id=pane_id, dead=False, exit_code=None)


def test_missing_pane_makes_live_session_unreachable() -> None:
    result = reconcile([make(A, Running())], [])
    assert result.updates == ((A, Unreachable()),)
    assert result.orphans == ()


def test_dead_pane_gives_exited_with_code() -> None:
    pane = PaneObservation(meute_id=A, dead=True, exit_code=7)
    assert reconcile([make(A, Running())], [pane]).updates == ((A, Exited(code=7)),)


def test_dead_pane_without_status_gives_exited_none() -> None:
    pane = PaneObservation(meute_id=A, dead=True, exit_code=None)
    assert reconcile([make(A, Running())], [pane]).updates == ((A, Exited(code=None)),)


def test_live_bash_pane_restores_running_from_unknown() -> None:
    assert reconcile([make(A, Unknown())], [alive(A)]).updates == ((A, Running()),)


def test_running_bash_with_live_pane_needs_no_update() -> None:
    result = reconcile([make(A, Running())], [alive(A)])
    assert (result.updates, result.orphans) == ((), ())


def test_claude_session_with_live_pane_is_untouched() -> None:
    result = reconcile([make(A, Idle(), AgentKind.CLAUDE)], [alive(A)])
    assert result.updates == ()


def test_ended_sessions_are_never_updated() -> None:
    result = reconcile([make(A, Exited(code=1)), make(B, Unreachable())], [alive(B)])
    assert result.updates == ()


def test_pane_of_an_ended_session_is_not_an_orphan() -> None:
    result = reconcile([make(A, Exited(code=0))], [alive(A)])
    assert result.orphans == ()


def test_unknown_and_malformed_ids_are_orphans_once() -> None:
    panes = [alive("not-a-uuid"), alive(B), alive("not-a-uuid")]
    assert reconcile([make(A, Running())], panes).orphans == ("not-a-uuid", B)


def test_updates_follow_session_order() -> None:
    result = reconcile([make(B, Running()), make(A, Running())], [])
    assert [u[0] for u in result.updates] == [B, A]


_IDS = st.sampled_from([A, B, SessionId("c"), SessionId("d")])
_STATES = st.sampled_from([Running(), Unknown(), Idle(), Exited(code=2), Unreachable()])
_SESSIONS = st.lists(
    st.builds(make, _IDS, _STATES, st.sampled_from(AgentKind)), unique_by=lambda s: s.id
)
_PANES = st.lists(
    st.builds(
        PaneObservation,
        meute_id=_IDS,
        dead=st.booleans(),
        exit_code=st.none() | st.integers(0, 255),
    )
)


@given(sessions=_SESSIONS, panes=_PANES)
def test_reconcile_invariants(sessions: list[Session], panes: list[PaneObservation]) -> None:
    result = reconcile(sessions, panes)
    live = {s.id for s in sessions if is_live(s.state)}
    known = {s.id for s in sessions}
    assert {sid for sid, _ in result.updates} <= live
    assert len(result.orphans) == len(set(result.orphans))
    assert not set(result.orphans) & known
