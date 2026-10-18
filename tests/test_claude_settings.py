"""Tests for the per-session --settings file."""

import shlex
import stat
from pathlib import Path

from meute.claude.settings import HOOK_EVENTS, settings_document, write_settings
from meute.core.json_types import JsonValue
from meute.core.session import SessionId
from support import load_json

FIXTURE = Path(__file__).parent / "fixtures" / "claude" / "2.1.302" / "settings.json"
TRICKY = ("/opt/it's here/python", "-m", "meute")


def _blank(value: JsonValue) -> JsonValue:
    """Copy of `value` with every `command` string replaced by a placeholder."""
    if isinstance(value, dict):
        return {
            k: "X" if k == "command" and isinstance(v, str) else _blank(v) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_blank(item) for item in value]
    return value


def _commands(value: JsonValue) -> list[str]:
    """Every `command` string found in `value`, in document order."""
    if isinstance(value, dict):
        return [
            c
            for k, v in value.items()
            for c in ([v] if k == "command" and isinstance(v, str) else _commands(v))
        ]
    if isinstance(value, list):
        return [c for item in value for c in _commands(item)]
    return []


def test_matches_captured_structure_up_to_commands() -> None:
    captured = load_json(FIXTURE.read_text(encoding="utf-8"))
    ours = settings_document(("meute",))
    assert _blank(ours) == _blank(captured)
    assert list(ours["hooks"]) == list(HOOK_EVENTS) if isinstance(ours["hooks"], dict) else False


def test_commands_are_quoted() -> None:
    commands = _commands(settings_document(TRICKY))
    expected = [shlex.join([*TRICKY, "ingest", "hook", e]) for e in HOOK_EVENTS]
    expected.append(shlex.join([*TRICKY, "ingest", "statusline"]))
    assert commands == expected
    assert all(shlex.split(c)[: len(TRICKY)] == list(TRICKY) for c in commands)


def test_write_settings_permissions_and_content(tmp_path: Path) -> None:
    session_id = SessionId("0b6f1d0e-0000-4000-8000-000000000001")
    path = write_settings(tmp_path / "state", session_id, TRICKY)
    assert path == tmp_path / "state" / "sessions" / session_id / "settings.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert load_json(path.read_text(encoding="utf-8")) == settings_document(TRICKY)


def test_write_settings_replaces_existing_file(tmp_path: Path) -> None:
    session_id = SessionId("0b6f1d0e-0000-4000-8000-000000000002")
    path = write_settings(tmp_path, session_id, ("a",))
    path.chmod(0o644)
    again = write_settings(tmp_path, session_id, ("b",))
    assert again == path
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "b ingest" in path.read_text(encoding="utf-8")
    assert [p.name for p in path.parent.iterdir()] == ["settings.json"]
