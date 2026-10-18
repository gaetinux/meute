"""What meute knows about a Claude Code session beyond the generic session fields."""

from dataclasses import dataclass
from datetime import datetime

from meute.core.json_types import JsonObject


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaudeDetails:
    """The Claude-specific columns of a session; each is None until a hook reports it."""

    native_id: str | None = None
    transcript_path: str | None = None
    model: str | None = None
    permission_mode: str | None = None
    last_tool: str | None = None
    pending_permission: str | None = None
    last_message: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionEvent:
    """One entry of a session's event history."""

    session_id: str
    event: str
    detail: str
    created_at: datetime


def claude_details_to_json(details: ClaudeDetails) -> JsonObject:
    """Return the flat JSON form of `details`."""
    return {
        "native_id": details.native_id,
        "transcript_path": details.transcript_path,
        "model": details.model,
        "permission_mode": details.permission_mode,
        "last_tool": details.last_tool,
        "pending_permission": details.pending_permission,
        "last_message": details.last_message,
    }
