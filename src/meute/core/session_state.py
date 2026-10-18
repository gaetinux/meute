"""The state of a session and its text forms."""

from dataclasses import dataclass

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


_IDS: dict[type[SessionState], str] = {
    Running: "running",
    SubagentRunning: "subagent_running",
    Compacting: "compacting",
    PermissionRequested: "permission_requested",
    WaitingInput: "waiting_input",
    Idle: "idle",
    Exited: "exited",
    Unreachable: "unreachable",
    MaybeStuck: "maybe_stuck",
    Unknown: "unknown",
}

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

_LABELS: dict[type[SessionState], str] = {
    Running: "running",
    SubagentRunning: "subagent",
    Compacting: "compacting",
    PermissionRequested: "permission",
    WaitingInput: "waiting for your reply",
    Idle: "idle",
    Exited: "exited",
    Unreachable: "unreachable",
    MaybeStuck: "stuck?",
    Unknown: "unknown?",
}


def state_id(state: SessionState) -> str:
    """Return the identifier stored in the database for `state`."""
    return _IDS[type(state)]


def state_from_parts(state: str, code: int | None) -> SessionState:
    """Build a state from its identifier; `code` is read for `exited` only.

    Raises:
        InvalidInput: `state` is not a known identifier.
    """
    if state == _IDS[Exited]:
        return Exited(code=code)
    if state in _STATELESS:
        return _STATELESS[state]
    message = f"unknown session state: {state}"
    raise InvalidInput(message)


def is_live(state: SessionState) -> bool:
    """Return whether the session still runs: false for `Exited` and `Unreachable` only."""
    return not isinstance(state, Exited | Unreachable)


def state_label(state: SessionState) -> str:
    """Return the display text of `state`; assumed states carry a `?`."""
    if isinstance(state, Exited) and state.code is not None:
        return f"exited ({state.code})"
    return _LABELS[type(state)]


def state_to_json(state: SessionState) -> JsonObject:
    """Return the tagged JSON form of `state`."""
    if isinstance(state, Exited):
        return {"kind": "exited", "code": state.code}
    return {"kind": state_id(state)}
