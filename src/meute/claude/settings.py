"""The per-session `--settings` file: hooks and status line pointing back at meute."""

import json
import shlex
from collections.abc import Sequence
from pathlib import Path

from meute.core.config import write_atomic
from meute.core.json_types import JsonObject
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


def settings_document(meute_command: Sequence[str]) -> JsonObject:
    """Build the settings document; every command is shell-quoted from `meute_command`."""
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
    return {
        "hooks": hooks,
        "statusLine": {
            "type": "command",
            "command": shlex.join([*meute_command, "ingest", "statusline"]),
        },
    }


def write_settings(state_dir: Path, session_id: SessionId, meute_command: Sequence[str]) -> Path:
    """Write `<state_dir>/sessions/<id>/settings.json` (folder 0700, file 0600) and return it."""
    folder = state_dir / "sessions" / session_id
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder.chmod(0o700)
    path = folder / "settings.json"
    # The temporary file is created 0600 and renamed over the target, so the mode holds.
    write_atomic(path, json.dumps(settings_document(meute_command), indent=2) + "\n")
    return path
