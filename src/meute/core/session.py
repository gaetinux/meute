"""The session model and its JSON form."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import NewType

from meute.core.errors import InvalidInput
from meute.core.instants import format_instant
from meute.core.json_types import JsonObject
from meute.core.project import ProjectId, RepoId
from meute.core.session_state import SessionState, state_to_json
from meute.core.task import TaskId

SessionId = NewType("SessionId", str)

_SHORT_ID_LENGTH = 8


class AgentKind(Enum):
    """What runs in a session."""

    CLAUDE = "claude"
    BASH = "bash"


def new_session_id() -> SessionId:
    """Return a fresh identifier: a lower-case hyphenated UUID."""
    return SessionId(str(uuid.uuid4()))


def parse_session_id(text: str) -> SessionId:
    """Return the canonical (lower-case, hyphenated) form of the UUID `text`.

    Raises:
        InvalidInput: `text` is not a UUID in hyphenated form.
    """
    try:
        parsed = uuid.UUID(text)
    except ValueError:
        parsed = None
    if parsed is None or str(parsed) != text.lower():
        message = f"invalid session id: {text}"
        raise InvalidInput(message)
    return SessionId(str(parsed))


def short_id(session_id: SessionId) -> str:
    """Return the first 8 characters of `session_id`."""
    return session_id[:_SHORT_ID_LENGTH]


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    """A session as stored in the database."""

    id: SessionId
    agent: AgentKind
    title: str
    project_id: ProjectId | None
    repo_id: RepoId | None
    task_id: TaskId | None
    cwd: Path
    state: SessionState
    last_activity_at: datetime
    created_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True, slots=True, kw_only=True)
class NewSession:
    """A session to create."""

    id: SessionId
    agent: AgentKind
    title: str
    cwd: Path
    state: SessionState
    project_id: ProjectId | None = None
    repo_id: RepoId | None = None
    task_id: TaskId | None = None
    permission_mode: str | None = None  # what meute asked Claude for; hooks refine it


def session_to_json(session: Session) -> JsonObject:
    """Return the flat JSON form of `session`."""
    return {
        "id": session.id,
        "agent": session.agent.value,
        "title": session.title,
        "project_id": session.project_id,
        "repo_id": session.repo_id,
        "task_id": session.task_id,
        "cwd": str(session.cwd),
        "state": state_to_json(session.state),
        "last_activity_at": format_instant(session.last_activity_at),
        "created_at": format_instant(session.created_at),
        "ended_at": None if session.ended_at is None else format_instant(session.ended_at),
    }
