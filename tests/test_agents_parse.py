"""Parsing `claude agents --json`."""

from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from meute.core.agents import AgentInfo, parse_agents

_FIXTURE = Path(__file__).parent / "fixtures/claude/2.1.302/agents.json"


def test_parses_the_captured_output() -> None:
    first, second = parse_agents(_FIXTURE.read_text(encoding="utf-8"))
    assert first == AgentInfo(
        pid=388326,
        cwd="/home/user/git/poc-app-rust",
        kind="interactive",
        session_id="7393e221-2a26-44ab-ae9c-fc905efac6e6",
        name="meute-capture",
        status="idle",
    )
    assert second.name == "-meute-capture-dash"


def test_unreadable_text_gives_nothing() -> None:
    assert parse_agents("") == ()
    assert parse_agents("{}") == ()
    assert parse_agents("not json") == ()
    assert parse_agents('[1, null, "x"]') == ()


def test_entry_without_pid_is_ignored() -> None:
    text = (
        '[{"cwd": "/a", "kind": "k", "sessionId": "s", "name": "n", "status": "idle"},'
        ' {"pid": 4, "cwd": "/b", "kind": "k", "sessionId": "t", "name": "m", "status": "busy"}]'
    )
    (only,) = parse_agents(text)
    assert only.pid == 4
    assert only.cwd == "/b"


def test_entry_with_wrong_types_is_ignored() -> None:
    text = '[{"pid": "4", "cwd": "/b", "kind": "k", "sessionId": "t", "name": "m", "status": "x"}]'
    assert parse_agents(text) == ()
    boolean = (
        '[{"pid": true, "cwd": "/b", "kind": "k", "sessionId": "t", "name": "m", "status": "x"}]'
    )
    assert parse_agents(boolean) == ()


@given(st.text())
def test_never_raises(text: str) -> None:
    assert isinstance(parse_agents(text), tuple)
