"""Which sessions need attention, and the M-n / M-N order."""

from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.attention import attention_count, needs_attention, next_attention
from meute.core.session import Session, SessionId
from meute.core.session_state import (
    Compacting,
    Exited,
    Idle,
    MaybeStuck,
    PermissionRequested,
    Running,
    SessionState,
    SubagentRunning,
    Unknown,
    Unreachable,
    WaitingInput,
)
from support import board_session

ID_A = SessionId("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
ID_B = SessionId("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ID_C = SessionId("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
ID_D = SessionId("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
ALL_STATES: list[SessionState] = [
    Running(),
    SubagentRunning(),
    Compacting(),
    PermissionRequested(),
    WaitingInput(),
    Idle(),
    Exited(code=0),
    Exited(code=None),
    Unreachable(),
    MaybeStuck(),
    Unknown(),
]


def session(session_id: SessionId, state: SessionState) -> Session:
    return replace(board_session(session_id, "s", Path("/work"), None, exited=False), state=state)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (Running(), False),
        (SubagentRunning(), False),
        (Compacting(), False),
        (PermissionRequested(), True),
        (WaitingInput(), True),
        (Idle(), False),
        (Exited(code=0), False),
        (Exited(code=None), False),
        (Unreachable(), False),
        (MaybeStuck(), True),
        (Unknown(), False),
    ],
)
def test_needs_attention(state: SessionState, expected: bool) -> None:  # noqa: FBT001 — parametrized
    assert needs_attention(state) is expected


def abc() -> list[Session]:
    return [session(ID_A, Idle()), session(ID_B, WaitingInput()), session(ID_C, MaybeStuck())]


def test_attention_count() -> None:
    assert attention_count(abc()) == 2
    assert attention_count([]) == 0


def test_next_attention_wraps_both_ways() -> None:
    order = abc()
    assert next_attention(order, ID_B) == order[2]
    assert next_attention(order, ID_C) == order[1]
    assert next_attention(order, ID_B, backwards=True) == order[2]
    assert next_attention(order, ID_C, backwards=True) == order[1]


def test_next_attention_from_a_quiet_or_unknown_session() -> None:
    order = abc()
    assert next_attention(order, ID_A) == order[1]
    assert next_attention(order, ID_A, backwards=True) == order[2]
    assert next_attention(order, None) == order[1]
    assert next_attention(order, None, backwards=True) == order[2]
    assert next_attention(order, ID_D) == order[1]
    assert next_attention(order, ID_D, backwards=True) == order[2]


def test_next_attention_after_a_quiet_session_in_the_middle() -> None:
    order = [session(ID_A, WaitingInput()), session(ID_B, Idle()), session(ID_C, MaybeStuck())]
    assert next_attention(order, ID_B) == order[2]
    assert next_attention(order, ID_B, backwards=True) == order[0]


def test_next_attention_alone_is_itself() -> None:
    order = [session(ID_A, Idle()), session(ID_B, WaitingInput())]
    assert next_attention(order, ID_B) == order[1]
    assert next_attention(order, ID_B, backwards=True) == order[1]


def test_no_session_needs_attention() -> None:
    order = [session(ID_A, Idle()), session(ID_B, Running())]
    assert next_attention(order, ID_A) is None
    assert next_attention(order, None, backwards=True) is None
    assert next_attention([], None) is None


@given(
    states=st.lists(st.sampled_from(ALL_STATES), max_size=8),
    pick=st.integers(min_value=-1, max_value=9),
    backwards=st.booleans(),
)
def test_result_always_needs_attention(
    states: list[SessionState],
    pick: int,
    backwards: bool,  # noqa: FBT001 — hypothesis
) -> None:
    order = [
        session(SessionId(f"{i:08d}-0000-4000-8000-000000000000"), s) for i, s in enumerate(states)
    ]
    current = order[pick].id if 0 <= pick < len(order) else None
    found = next_attention(order, current, backwards=backwards)
    assert (found is None) == (attention_count(order) == 0)
    if found is not None:
        assert needs_attention(found.state)
        assert found in order
