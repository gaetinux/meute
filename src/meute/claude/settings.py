"""The per-session `--settings` file: hooks and status line pointing back at meute."""

import json
import shlex
from collections.abc import Sequence
from pathlib import Path

from meute.core.config import write_atomic
from meute.core.json_types import JsonObject
from meute.core.mcp_data import MCP_SERVER_NAME, MCP_TOOL_NAMES
from meute.core.paths import make_private_dir
from meute.core.session import SessionId

HOOK_EVENTS: tuple[str, ...] = (
    "SessionStart",
    "UserPromptSubmit",
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PreCompact",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "SessionEnd",
    "Notification",
)


MEUTE_TOOLS: tuple[str, ...] = tuple(f"mcp__{MCP_SERVER_NAME}__{name}" for name in MCP_TOOL_NAMES)


def settings_document(
    meute_command: Sequence[str], allowed_tools: Sequence[str] = ()
) -> JsonObject:
    """Build the settings document; every command is shell-quoted from `meute_command`.

    A non-empty `allowed_tools` is added as `permissions.allow`.
    """
    hooks: JsonObject = {
        event: [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": shlex.join([*meute_command, "ingest", "hook", event]),
                    }
                ]
            }
        ]
        for event in HOOK_EVENTS
    }
    document: JsonObject = {
        "hooks": hooks,
        "statusLine": {
            "type": "command",
            "command": shlex.join([*meute_command, "ingest", "statusline"]),
        },
    }
    if allowed_tools:
        document["permissions"] = {"allow": list(allowed_tools)}
    return document


def write_session_file(state_dir: Path, session_id: SessionId, name: str, text: str) -> Path:
    """Write `<state_dir>/sessions/<id>/<name>` (folders 0700, file 0600) and return it.

    A file that already holds `text` is left in place, only made 0600 again.
    """
    folder = state_dir / "sessions" / session_id
    make_private_dir(folder)
    for parent in (state_dir, folder.parent):
        parent.chmod(0o700)
    path = folder / name
    if _holds(path, text):
        path.chmod(0o600)
        return path
    # The temporary file is created 0600 and renamed over the target, so the mode holds.
    write_atomic(path, text)
    return path


def _holds(path: Path, text: str) -> bool:
    try:
        return path.read_bytes() == text.encode("utf-8")  # bytes: no newline translation
    except OSError:
        return False


def write_settings(
    state_dir: Path,
    session_id: SessionId,
    meute_command: Sequence[str],
    allowed_tools: Sequence[str] = (),
) -> Path:
    """Write `<state_dir>/sessions/<id>/settings.json` (folders 0700, file 0600) and return it."""
    text = json.dumps(settings_document(meute_command, allowed_tools), indent=2) + "\n"
    return write_session_file(state_dir, session_id, "settings.json", text)
