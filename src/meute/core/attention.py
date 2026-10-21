"""Which sessions need the user's attention, and the order to visit them or to show next."""

from collections.abc import Sequence
from typing import assert_never

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
    is_live,
)


def needs_attention(state: SessionState) -> bool:
    """Return whether a session in `state` waits for the user."""
    match state:
        case PermissionRequested() | WaitingInput() | MaybeStuck():
            return True
        case Running() | SubagentRunning() | Compacting() | Idle():
            return False
        case Exited() | Unreachable() | Unknown():
            return False
        case _:
            assert_never(state)


def attention_count(sessions: Sequence[Session]) -> int:
    """Return how many of `sessions` need attention."""
    return sum(1 for session in sessions if needs_attention(session.state))


def next_attention(
    order: Sequence[Session], current: SessionId | None, *, backwards: bool = False
) -> Session | None:
    """Return the session needing attention that follows (or precedes) `current` in `order`.

    The search wraps around and ends on `current` itself, so a lone session needing attention
    is returned as is. A `current` that is absent or not in `order` starts from the first
    (or, backwards, the last) session. Returns None when no session needs attention.
    """
    size = len(order)
    position = next((i for i, session in enumerate(order) if session.id == current), None)
    step = -1 if backwards else 1
    if position is None:
        start, count = (size - 1, size) if backwards else (0, size)
    else:
        start, count = position + step, size
    for offset in range(count):
        candidate = order[(start + offset * step) % size]
        if needs_attention(candidate.state):
            return candidate
    return None


def next_live(order: Sequence[Session], current: str) -> Session | None:
    """Return the live session that follows `current` in `order`, to show once it is stopped.

    The search wraps around and never returns `current` itself. A `current` that is not in
    `order` (an orphan pane, say) starts from the first session. Returns None when no other
    session is live.
    """
    position = next((i for i, session in enumerate(order) if session.id == current), -1)
    size = len(order)
    for offset in range(1, size + 1):
        candidate = order[(position + offset) % size]
        if candidate.id != current and is_live(candidate.state):
            return candidate
    return None
