"""Saved states: the open sessions kept under a name, their JSON form, names and texts."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.errors import InvalidInput
from meute.core.json_types import JsonObject, JsonValue
from meute.core.project import RepoId
from meute.core.session import AgentKind, SessionId, parse_session_id
from meute.core.sessions_view_text import age_text
from meute.core.task import TaskId
from meute.core.text import one_line, printable

LAST = "last"
"""The state the board keeps up to date with the open sessions; no one else names a state so."""

RETAINED = 10
"""How many named states are kept, `last` aside."""

NAME_LIMIT = 60
"""The longest name of a state, in characters."""

_MAX_DB_ID = 2**63 - 1
_AGENTS = {kind.value: kind for kind in AgentKind}


@dataclass(frozen=True, slots=True, kw_only=True)
class SavedSession:
    """One session of a saved state, enough to reopen it."""

    session_id: SessionId
    agent: AgentKind
    cwd: Path
    native_id: str | None
    title: str
    task_id: TaskId | None
    repo_id: RepoId | None
    displayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SavedState:
    """The sessions saved under `name`, in the order of the board, at `created_at`."""

    name: str
    created_at: datetime
    sessions: tuple[SavedSession, ...]


def _session_json(session: SavedSession) -> JsonObject:
    return {
        "session_id": session.session_id,
        "agent": session.agent.value,
        "cwd": str(session.cwd),
        "native_id": session.native_id,
        "title": session.title,
        "task_id": session.task_id,
        "repo_id": session.repo_id,
        "displayed": session.displayed,
    }


def sessions_json(sessions: Sequence[SavedSession]) -> str:
    """Return the compact JSON array that stores `sessions`."""
    return json.dumps([_session_json(session) for session in sessions], separators=(",", ":"))


def _db_id(value: JsonValue) -> int | None:
    """Return `value` if it is a database id (a positive 64-bit integer), else None."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= _MAX_DB_ID:
        return None
    return value


def _session_id(value: JsonValue) -> SessionId | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = parse_session_id(value)
    except InvalidInput:
        return None
    return parsed if parsed == value else None


def _cwd(value: JsonValue) -> Path | None:
    if not isinstance(value, str):
        return None
    path = Path(value)
    return path if path.is_absolute() else None


def _optional_id(entry: dict[str, JsonValue], key: str) -> tuple[bool, int | None]:
    """Return whether `entry[key]` is null or a database id, and that id."""
    value = entry.get(key)
    db_id = _db_id(value)
    return (key in entry and value is None) or db_id is not None, db_id


def _session(entry: JsonValue) -> SavedSession | None:
    if not isinstance(entry, dict):
        return None
    session_id = _session_id(entry.get("session_id"))
    agent = entry.get("agent")
    kind = _AGENTS.get(agent) if isinstance(agent, str) else None
    cwd = _cwd(entry.get("cwd"))
    native_id, title, displayed = (entry.get(key) for key in ("native_id", "title", "displayed"))
    task_ok, task_id = _optional_id(entry, "task_id")
    repo_ok, repo_id = _optional_id(entry, "repo_id")
    if (
        session_id is None
        or kind is None
        or cwd is None
        or not ("native_id" in entry and (native_id is None or isinstance(native_id, str)))
        or not isinstance(title, str)
        or not isinstance(displayed, bool)
        or not task_ok
        or not repo_ok
    ):
        return None
    return SavedSession(
        session_id=session_id,
        agent=kind,
        cwd=cwd,
        native_id=native_id,
        title=title,
        task_id=None if task_id is None else TaskId(task_id),
        repo_id=None if repo_id is None else RepoId(repo_id),
        displayed=displayed,
    )


def parse_sessions(text: str) -> tuple[SavedSession, ...]:
    """Read the sessions stored by `sessions_json`; never raises.

    An unreadable entry (missing field, wrong type, invalid id, relative folder, unknown agent)
    is skipped; an unreadable document gives no session.
    """
    try:
        loaded: JsonValue = json.loads(text)  # pyright: ignore[reportAny] — json.loads returns Any
    except (ValueError, RecursionError):
        return ()
    if not isinstance(loaded, list):
        return ()
    sessions = (_session(entry) for entry in loaded)
    return tuple(session for session in sessions if session is not None)


def state_name(text: str) -> str:
    """Return the name a user gives to a state, on one line of at most `NAME_LIMIT` characters.

    Raises:
        InvalidInput: the name is empty, or is `last` (kept by the board).
    """
    name = one_line(text.strip(), NAME_LIMIT)
    if not name:
        message = "state name is empty"
        raise InvalidInput(message)
    if name == LAST:
        message = "last is kept by the board"
        raise InvalidInput(message)
    return name


def stamp_name(now: datetime) -> str:
    """Return the name of a state saved without one: `now` as `YYYY-MM-DD HH:MM`."""
    return now.strftime("%Y-%m-%d %H:%M")


NO_SAVED_STATE = "no saved state"
"""What the board's list of saved states shows when there is none."""


def saved_text(name: str) -> str:
    """Return what the board tells once it saved a state under `name`."""
    return f"state saved: {printable(name)}"


def reopening_text(name: str) -> str:
    """Return what the board tells while it reopens the state `name`."""
    return f"reopening {printable(name)}…"


def reopen_text(reopened: int, skipped: Sequence[tuple[str, str]]) -> list[str]:
    """Return the report of a reopening: the counts, then `  <title>: <reason>` per skip."""
    return [
        f"reopened {reopened} · skipped {len(skipped)}",
        *(f"  {printable(title)}: {printable(reason)}" for title, reason in skipped),
    ]


def state_line(state: SavedState, now: datetime) -> str:
    """Return `<name>  <n> sessions  <age>`, with `1 session` in the singular."""
    count = len(state.sessions)
    sessions = "1 session" if count == 1 else f"{count} sessions"
    return f"{printable(state.name)}  {sessions}  {age_text(state.created_at, now)}"
