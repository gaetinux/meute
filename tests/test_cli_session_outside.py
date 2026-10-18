"""`meute session list` with sessions outside meute, through the fake `claude`."""

from pathlib import Path

from conftest import Sandbox
from support import load_json

_AGENTS = (
    '[{"pid": 5, "cwd": "%s", "kind": "interactive", "sessionId": "ext-1",'
    ' "name": "side job", "status": "busy"}]'
)


def _agents_file(sandbox: Sandbox, text: str | None = None) -> Path:
    path = sandbox.root / "agents.json"
    path.write_text(text if text is not None else _AGENTS % (sandbox.root / "home" / "proj"))
    return path


def test_outside_line_after_the_sessions(sandbox: Sandbox) -> None:
    path = _agents_file(sandbox)
    result = sandbox.run("session", "list", env={"MEUTE_FAKE_CLAUDE_AGENTS": str(path)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == "outside: busy  side job  ~/proj\n"


def test_json_has_the_outside_key(sandbox: Sandbox) -> None:
    path = _agents_file(sandbox)
    result = sandbox.run("session", "list", "--json", env={"MEUTE_FAKE_CLAUDE_AGENTS": str(path)})
    loaded = load_json(result.stdout)
    assert isinstance(loaded, dict)
    outside = loaded["outside"]
    assert isinstance(outside, list)
    (entry,) = outside
    assert isinstance(entry, dict)
    assert entry["session_id"] == "ext-1"
    assert entry["status"] == "busy"


def test_nothing_outside_prints_nothing_extra(sandbox: Sandbox) -> None:
    result = sandbox.run("session", "list")
    assert result.stdout == ""
    loaded = load_json(sandbox.run("session", "list", "--json").stdout)
    assert isinstance(loaded, dict)
    assert "outside" not in loaded  # absent when empty: keeps the pinned JSON shape


def test_failing_claude_agents_leaves_the_normal_list(sandbox: Sandbox) -> None:
    missing = sandbox.root / "does-not-exist.json"
    result = sandbox.run("session", "list", env={"MEUTE_FAKE_CLAUDE_AGENTS": str(missing)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    garbage = _agents_file(sandbox, "{{{")
    result = sandbox.run("session", "list", env={"MEUTE_FAKE_CLAUDE_AGENTS": str(garbage)})
    assert result.returncode == 0
    assert result.stdout == ""


def test_escape_sequences_in_names_are_neutralised(sandbox: Sandbox) -> None:
    text = (
        '[{"pid": 5, "cwd": "/x", "kind": "i", "sessionId": "e", '
        '"name": "a\\u001b[31mb", "status": "idle"}]'
    )
    path = _agents_file(sandbox, text)
    result = sandbox.run("session", "list", env={"MEUTE_FAKE_CLAUDE_AGENTS": str(path)})
    assert "\x1b" not in result.stdout
