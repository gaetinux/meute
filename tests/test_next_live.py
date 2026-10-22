"""Which session to show once the displayed one is stopped."""

from dataclasses import replace
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from meute.core.attention import next_live
from meute.core.session import Session, SessionId
from meute.core.session_state import Exited, Idle, Running, SessionState, Unreachable, WaitingInput
from support import board_session

ID_A = SessionId("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ID_B = SessionId("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ID_C = SessionId("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ID_D = SessionId("dddddddd-dddd-4ddd-8ddd-dddddddddddd")


def _session(session_id: SessionId, state: SessionState) -> Session:
    return replace(board_session(session_id, "s", Path("/work"), None, exited=False), state=state)


def test_the_next_live_session_follows_the_stopped_one() -> None:
    order = [_session(ID_A, Running()), _session(ID_B, Idle()), _session(ID_C, Running())]
    assert next_live(order, ID_B) == order[2]


def test_the_search_wraps_around() -> None:
    order = [_session(ID_A, Running()), _session(ID_B, Idle()), _session(ID_C, Running())]
    assert next_live(order, ID_C) == order[0]


def test_ended_sessions_are_skipped() -> None:
    order = [
        _session(ID_A, WaitingInput()),
        _session(ID_B, Running()),
        _session(ID_C, Exited(code=0)),
        _session(ID_D, Unreachable()),
    ]
    assert next_live(order, ID_B) == order[0]


def test_the_stopped_session_itself_is_never_chosen() -> None:
    order = [_session(ID_A, Running()), _session(ID_B, Exited(code=0))]
    assert next_live(order, ID_A) is None


def test_an_absent_current_starts_from_the_first() -> None:
    order = [_session(ID_A, Exited(code=0)), _session(ID_B, Idle()), _session(ID_C, Running())]
    assert next_live(order, "orphan-id") == order[1]


def test_nothing_live_gives_none() -> None:
    assert next_live([], ID_A) is None
    assert next_live([_session(ID_B, Exited(code=1))], ID_A) is None


@given(
    st.lists(st.sampled_from([Running(), Idle(), Exited(code=0), Unreachable()]), max_size=6),
    st.integers(min_value=0, max_value=6),
)
def test_the_result_is_live_and_not_the_current(states: list[SessionState], index: int) -> None:
    ids = [SessionId(f"{n:08x}-aaaa-4aaa-8aaa-aaaaaaaaaaaa") for n in range(len(states))]
    order = [_session(i, s) for i, s in zip(ids, states, strict=True)]
    current = ids[index] if index < len(ids) else ID_D
    result = next_live(order, current)
    others = [s for s in order if s.id != current and isinstance(s.state, Running | Idle)]
    assert (result is None) == (not others)
    if result is not None:
        assert result.id != current
        assert isinstance(result.state, Running | Idle)
