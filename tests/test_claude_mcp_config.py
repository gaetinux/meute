"""Tests for the per-session --mcp-config file and the tools allowed in --settings."""

import stat
from pathlib import Path

from meute.claude.mcp_config import mcp_config_document, write_mcp_config
from meute.claude.settings import MEUTE_TOOLS, settings_document
from meute.core.session import SessionId
from support import load_json

SID = SessionId("0b6f1d0e-0000-4000-8000-000000000003")
COMMAND = ("/opt/it's here/python", "-m", "meute")


def test_document_is_a_stdio_server_bound_to_the_session() -> None:
    assert mcp_config_document(COMMAND, SID) == {
        "mcpServers": {
            "meute": {
                "type": "stdio",
                "command": "/opt/it's here/python",
                "args": ["-m", "meute", "mcp"],
                "env": {"MEUTE_SESSION": SID},
            }
        }
    }


def test_file_is_private_and_atomic(tmp_path: Path) -> None:
    state = tmp_path / "state"
    path = write_mcp_config(state, SID, COMMAND)
    assert path == state / "sessions" / SID / "mcp.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    for folder in (state, state / "sessions", path.parent):
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert load_json(path.read_text(encoding="utf-8")) == mcp_config_document(COMMAND, SID)
    assert sorted(p.name for p in path.parent.iterdir()) == ["mcp.json"]


def test_the_seven_tools_are_named_in_order() -> None:
    assert MEUTE_TOOLS == (
        "mcp__meute__task_list",
        "mcp__meute__task_read",
        "mcp__meute__task_create",
        "mcp__meute__task_update",
        "mcp__meute__task_set_status",
        "mcp__meute__task_note_add",
        "mcp__meute__task_link_session",
    )


def test_settings_allow_the_tools_only_when_given() -> None:
    assert "permissions" not in settings_document(COMMAND)
    allowed = settings_document(COMMAND, MEUTE_TOOLS)
    assert allowed["permissions"] == {"allow": list(MEUTE_TOOLS)}
