"""Claude sessions as `claude agents --json` reports them, and the states assumed from them."""

import json
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from meute.core.json_types import JsonValue
from meute.core.session import AgentKind, Session
from meute.core.session_state import (
    Idle,
    MaybeStuck,
    Running,
    SessionState,
    SubagentRunning,
    WaitingInput,
    is_live,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentInfo:
    """One running Claude process, as listed by `claude agents --json`."""

    pid: int
    cwd: str
    kind: str
    session_id: str
    name: str
    status: str


def _agent(entry: JsonValue) -> AgentInfo | None:
    if not isinstance(entry, dict):
        return None
    pid = entry.get("pid")
    cwd, kind, session_id, name, status = (
        entry.get(key) for key in ("cwd", "kind", "sessionId", "name", "status")
    )
    if (
        isinstance(pid, int)
        and not isinstance(pid, bool)
        and isinstance(cwd, str)
        and isinstance(kind, str)
        and isinstance(session_id, str)
        and isinstance(name, str)
        and isinstance(status, str)
    ):
        return AgentInfo(
            pid=pid, cwd=cwd, kind=kind, session_id=session_id, name=name, status=status
        )
    return None


def parse_agents(text: str) -> tuple[AgentInfo, ...]:
    """Parse the output of `claude agents --json`; incomplete entries and bad text give nothing."""
    try:
        loaded: JsonValue = json.loads(text)  # pyright: ignore[reportAny] — json.loads returns Any
    except (ValueError, RecursionError):
        return ()
    if not isinstance(loaded, list):
        return ()
    agents = (_agent(entry) for entry in loaded)
    return tuple(agent for agent in agents if agent is not None)


_OFFICIAL: dict[str, SessionState] = {
    "busy": Running(),
    "waiting": WaitingInput(),
    "idle": Idle(),
}


def assumed_state(
    session: Session, agent: AgentInfo | None, *, now: datetime, stuck_after: timedelta
) -> SessionState | None:
    """Return the state to record for a silent live Claude session, or `None` to keep it.

    Only a Claude session that is alive and silent for more than `stuck_after` is concerned.
    The official status of `agent` wins; without an agent a running session may be stuck.
    """
    if (
        session.agent is not AgentKind.CLAUDE
        or not is_live(session.state)
        or now - session.last_activity_at <= stuck_after
    ):
        return None
    if agent is not None:
        deduced = _OFFICIAL.get(agent.status)
    elif isinstance(session.state, Running | SubagentRunning):
        deduced = MaybeStuck()
    else:
        deduced = None
    return None if deduced == session.state else deduced


def outside_agents(
    agents: Sequence[AgentInfo],
    sessions: Sequence[Session],
    *,
    native_ids: Collection[str] = (),
) -> tuple[AgentInfo, ...]:
    """Return the agents whose id is neither a meute session's id nor one of `native_ids`."""
    known = {str(session.id) for session in sessions} | set(native_ids)
    return tuple(agent for agent in agents if agent.session_id not in known)
