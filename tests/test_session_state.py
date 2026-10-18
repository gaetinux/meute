"""Tests for the session state union."""

import pytest

from meute.core.errors import InvalidInput
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
    is_live,
    state_from_parts,
    state_id,
    state_label,
    state_to_json,
)

ALL_STATES: list[SessionState] = [
    Running(),
    SubagentRunning(),
    Compacting(),
    PermissionRequested(),
    WaitingInput(),
    Idle(),
    Exited(code=7),
    Exited(code=None),
    Unreachable(),
    MaybeStuck(),
    Unknown(),
]


@pytest.mark.parametrize("state", ALL_STATES)
def test_state_round_trips_through_its_parts(state: SessionState) -> None:
    code = state.code if isinstance(state, Exited) else None
    assert state_from_parts(state_id(state), code) == state


def test_state_ids() -> None:
    assert [state_id(state) for state in ALL_STATES] == [
        "running",
        "subagent_running",
        "compacting",
        "permission_requested",
        "waiting_input",
        "idle",
        "exited",
        "exited",
        "unreachable",
        "maybe_stuck",
        "unknown",
    ]


def test_code_is_only_read_for_exited() -> None:
    assert state_from_parts("running", 3) == Running()


@pytest.mark.parametrize(
    ("state", "live"),
    [
        (Running(), True),
        (SubagentRunning(), True),
        (Compacting(), True),
        (PermissionRequested(), True),
        (WaitingInput(), True),
        (Idle(), True),
        (MaybeStuck(), True),
        (Unknown(), True),
        (Exited(code=0), False),
        (Unreachable(), False),
    ],
)
def test_is_live(state: SessionState, live: bool) -> None:  # noqa: FBT001 — pytest parametrize argument
    assert is_live(state) is live


@pytest.mark.parametrize(
    ("state", "label"),
    [
        (Running(), "running"),
        (SubagentRunning(), "subagent"),
        (Compacting(), "compacting"),
        (PermissionRequested(), "permission"),
        (WaitingInput(), "waiting for your reply"),
        (Idle(), "idle"),
        (Exited(code=7), "exited (7)"),
        (Exited(code=None), "exited"),
        (Unreachable(), "unreachable"),
        (MaybeStuck(), "stuck?"),
        (Unknown(), "unknown?"),
    ],
)
def test_state_label(state: SessionState, label: str) -> None:
    assert state_label(state) == label


def test_state_json_shape() -> None:
    assert state_to_json(Exited(code=2)) == {"kind": "exited", "code": 2}
    assert state_to_json(Running()) == {"kind": "running"}


def test_unknown_state_id_is_rejected() -> None:
    with pytest.raises(InvalidInput, match=r"^unknown session state: asleep$"):
        state_from_parts("asleep", None)
