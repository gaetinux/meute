"""The per-session `--mcp-config` file: the meute MCP server, bound to its session."""

import json
from collections.abc import Sequence
from pathlib import Path

from meute.claude.settings import write_session_file
from meute.core.json_types import JsonObject
from meute.core.mcp_data import MCP_SERVER_NAME
from meute.core.session import SessionId


def mcp_config_document(meute_command: Sequence[str], session_id: SessionId) -> JsonObject:
    """Build the MCP configuration: one stdio server, `meute`, running `meute mcp`."""
    return {
        "mcpServers": {
            MCP_SERVER_NAME: {
                "type": "stdio",
                "command": meute_command[0],
                "args": [*meute_command[1:], "mcp"],
                "env": {"MEUTE_SESSION": session_id},
            }
        }
    }


def write_mcp_config(state_dir: Path, session_id: SessionId, meute_command: Sequence[str]) -> Path:
    """Write `<state_dir>/sessions/<id>/mcp.json` (folders 0700, file 0600) and return it."""
    text = json.dumps(mcp_config_document(meute_command, session_id), indent=2) + "\n"
    return write_session_file(state_dir, session_id, "mcp.json", text)
