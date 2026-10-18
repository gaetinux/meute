"""The state of a session and its text forms."""

from dataclasses import dataclass
from typing import assert_never

from meute.core.errors import InvalidInput
from meute.core.json_types import JsonObject


@dataclass(frozen=True, slots=True, kw_only=True)
class Running:
    """The agent is working."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SubagentRunning:
    """A subagent is working."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Compacting:
    """The conversation is being compacted."""


@dataclass(frozen=True, slots=True, kw_only=True)
class PermissionRequested:
    """The agent waits for a permission."""


@dataclass(frozen=True, slots=True, kw_only=True)
class WaitingInput:
    """The agent waits for the user's reply."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Idle:
    """The session is alive and doing nothing."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Exited:
    """The process ended; the exit code is known or not."""

    code: int | None


@dataclass(frozen=True, slots=True, kw_only=True)
class Unreachable:
    """The pane of the session is gone."""


@dataclass(frozen=True, slots=True, kw_only=True)
class MaybeStuck:
    """The session may be stuck (assumed state)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Unknown:
    """The state cannot be told (assumed state)."""


SessionState = (
    Running
    | SubagentRunning
    | Compacting
    | PermissionRequested
    | WaitingInput
    | Idle
    | Exited
    | Unreachable
    | MaybeStuck
    | Unknown
)


def state_id(state: SessionState) -> str:  # noqa: PLR0911, C901 — one return per session state
    """Return the identifier stored in the database for `state`."""
    match state:
        case Running():
            return "running"
        case SubagentRunning():
            return "subagent_running"
        case Compacting():
            return "compacting"
        case PermissionRequested():
            return "permission_requested"
        case WaitingInput():
            return "waiting_input"
        case Idle():
            return "idle"
        case Exited():
            return "exited"
        case Unreachable():
            return "unreachable"
        case MaybeStuck():
            return "maybe_stuck"
        case Unknown():
            return "unknown"
        case _:
            assert_never(state)


_STATELESS: dict[str, SessionState] = {
    "running": Running(),
    "subagent_running": SubagentRunning(),
    "compacting": Compacting(),
    "permission_requested": PermissionRequested(),
    "waiting_input": WaitingInput(),
    "idle": Idle(),
    "unreachable": Unreachable(),
    "maybe_stuck": MaybeStuck(),
    "unknown": Unknown(),
}


def state_from_parts(state: str, code: int | None) -> SessionState:
    """Build a state from its identifier; `code` is read for `exited` only.

    Raises:
        InvalidInput: `state` is not a known identifier.
    """
    if state == "exited":
        return Exited(code=code)
    if state in _STATELESS:
        return _STATELESS[state]
    message = f"unknown session state: {state}"
    raise InvalidInput(message)


def is_live(state: SessionState) -> bool:
    """Return whether the session still runs: false for `Exited` and `Unreachable` only."""
    match state:
        case Exited() | Unreachable():
            return False
        case (
            Running()
            | SubagentRunning()
            | Compacting()
            | PermissionRequested()
            | WaitingInput()
            | Idle()
            | MaybeStuck()
            | Unknown()
        ):
            return True
        case _:
            assert_never(state)


def state_label(state: SessionState) -> str:  # noqa: PLR0911, C901 — one return per session state
    """Return the display text of `state`; assumed states carry a `?`."""
    match state:
        case Running():
            return "running"
        case SubagentRunning():
            return "subagent"
        case Compacting():
            return "compacting"
        case PermissionRequested():
            return "permission"
        case WaitingInput():
            return "waiting for your reply"
        case Idle():
            return "idle"
        case Exited(code=None):
            return "exited"
        case Exited(code=code):
            return f"exited ({code})"
        case Unreachable():
            return "unreachable"
        case MaybeStuck():
            return "stuck?"
        case Unknown():
            return "unknown?"
        case _:
            assert_never(state)


def state_to_json(state: SessionState) -> JsonObject:
    """Return the tagged JSON form of `state`."""
    match state:
        case Exited():
            return {"kind": "exited", "code": state.code}
        case (
            Running()
            | SubagentRunning()
            | Compacting()
            | PermissionRequested()
            | WaitingInput()
            | Idle()
            | Unreachable()
            | MaybeStuck()
            | Unknown()
        ):
            return {"kind": state_id(state)}
        case _:
            assert_never(state)
