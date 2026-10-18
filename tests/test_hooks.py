"""Interpretation of Claude Code hooks into session states (real 2.1.302 payloads)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from meute.core.hooks import HookEffect, interpret_hook, tool_excerpt
from meute.core.json_types import JsonValue
from meute.core.session_state import (
    Compacting,
    Exited,
    Idle,
    PermissionRequested,
    Running,
    SubagentRunning,
    WaitingInput,
)
from support import claude_fixture


def test_session_start() -> None:
    effect = interpret_hook("SessionStart", claude_fixture("SessionStart-1"))
    assert effect is not None
    assert effect.state == Idle()
    assert effect.native_id == "7393e221-2a26-44ab-ae9c-fc905efac6e6"
    assert (
        effect.transcript_path
        == "/home/user/.claude/projects/x/7393e221-2a26-44ab-ae9c-fc905efac6e6.jsonl"
    )
    assert effect.model == "claude-opus-5-5"


def test_session_start_model_object() -> None:
    effect = interpret_hook("SessionStart", {"session_id": "s", "model": {"id": "m-1"}})
    assert effect is not None
    assert effect.model == "m-1"


def test_user_prompt_submit_records_manual_for_default() -> None:
    effect = interpret_hook("UserPromptSubmit", claude_fixture("UserPromptSubmit-1"))
    assert effect is not None
    assert effect.state == Running()
    assert effect.permission_mode == "manual"  # S7: Claude reports meute's manual mode as default


def test_user_prompt_submit_keeps_other_modes() -> None:
    effect = interpret_hook("UserPromptSubmit", {"permission_mode": "plan"})
    assert effect is not None
    assert effect.permission_mode == "plan"


def test_pre_tool_use() -> None:
    effect = interpret_hook("PreToolUse", claude_fixture("PreToolUse-1"))
    assert effect is not None
    assert effect.state == Running()
    assert effect.last_tool == "Bash echo meute-capture"


def test_permission_request() -> None:
    effect = interpret_hook("PermissionRequest", claude_fixture("PermissionRequest-1"))
    assert effect is not None
    assert effect.state == PermissionRequested()
    assert effect.pending_permission == "Bash mkdir /tmp/capture/denied"


def test_post_tool_use() -> None:
    effect = interpret_hook("PostToolUse", claude_fixture("PostToolUse-1"))
    assert effect is not None
    assert effect.state == Running()
    assert effect.last_tool is None


def test_pre_compact() -> None:
    effect = interpret_hook("PreCompact", claude_fixture("PreCompact-1"))
    assert effect is not None
    assert effect.state == Compacting()


def test_subagent_start_and_stop() -> None:
    start = interpret_hook("SubagentStart", claude_fixture("SubagentStart-1"))
    stop = interpret_hook("SubagentStop", claude_fixture("SubagentStop-1"))
    assert start is not None
    assert start.state == SubagentRunning()
    assert stop is not None
    assert stop.state == Running()


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        ("SubagentStop", "SubagentStop-2"),  # /compact noise: agent_type is empty
        ("SubagentStop", "SubagentStop-3"),
    ],
)
def test_subagent_hooks_without_agent_type_are_ignored(event: str, payload: str) -> None:
    assert interpret_hook(event, claude_fixture(payload)) is None


@pytest.mark.parametrize("event", ["SubagentStart", "SubagentStop"])
def test_subagent_hooks_with_missing_agent_type_are_ignored(event: str) -> None:
    assert interpret_hook(event, {}) is None


def test_stop() -> None:
    effect = interpret_hook("Stop", claude_fixture("Stop-2"))
    assert effect is not None
    assert effect.state == WaitingInput()
    assert effect.last_message == "La commande a affiché `meute-capture`."


def test_stop_message_is_cut_at_500_characters() -> None:
    effect = interpret_hook("Stop", {"last_assistant_message": "x" * 900})
    assert effect is not None
    assert effect.last_message == "x" * 500


def test_background_subagent_sequence_ends_waiting() -> None:
    # S7: Stop, then a <task-notification> prompt, then a second Stop: no special case.
    prompt = interpret_hook("UserPromptSubmit", claude_fixture("UserPromptSubmit-5"))
    stop = interpret_hook("Stop", claude_fixture("Stop-4"))
    assert prompt is not None
    assert prompt.state == Running()
    assert stop is not None
    assert stop.state == WaitingInput()


def test_session_end() -> None:
    effect = interpret_hook("SessionEnd", claude_fixture("SessionEnd-1"))
    assert effect is not None
    assert effect.state == Exited(code=None)


def test_notification_is_history_only() -> None:
    # No Notification was captured in S7: this payload is hand-written from the documented shape.
    effect = interpret_hook("Notification", {"message": "Claude needs your permission"})
    assert effect == HookEffect(state=None, history="Claude needs your permission")


def test_unknown_event_is_history_only() -> None:
    assert interpret_hook("FutureEvent", {}) == HookEffect(state=None, history="FutureEvent")


@pytest.mark.parametrize(
    ("name", "tool_input", "expected"),
    [
        ("Bash", {"command": "ls -l", "description": "d"}, "Bash ls -l"),
        ("Edit", {"file_path": "/a/b.py", "old_string": "x"}, "Edit /a/b.py"),
        ("Read", {"file_path": "/a"}, "Read /a"),
        ("mcp__x__tool", {"n": 3, "q": "find me"}, "mcp__x__tool find me"),
        ("mcp__x__tool", {"n": 3}, "mcp__x__tool"),
        ("Bash", "not a mapping", "Bash"),
        ("Bash", {"command": "line one\nline two"}, "Bash line one line two"),
        ("Bash", {"command": "x" * 200}, "Bash " + "x" * 79 + "…"),
        ("Bash", {"command": "x" * 80}, "Bash " + "x" * 80),
        ("Bash", {"command": "a\x1b[31mb"}, "Bash a�[31mb"),
    ],
)
def test_tool_excerpt(name: str, tool_input: object, expected: str) -> None:
    assert tool_excerpt(name, tool_input) == expected


json_values = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats() | st.text(),
    lambda children: st.lists(children) | st.dictionaries(st.text(), children),
    max_leaves=8,
)


@given(event=st.text(), payload=st.dictionaries(st.text(), json_values))
def test_interpret_hook_never_raises(event: str, payload: dict[str, JsonValue]) -> None:
    interpret_hook(event, payload)


@given(
    event=st.sampled_from(
        [
            "SessionStart",
            "UserPromptSubmit",
            "PreToolUse",
            "PermissionRequest",
            "Stop",
            "SubagentStart",
            "SubagentStop",
            "Notification",
        ]
    ),
    payload=st.dictionaries(
        st.sampled_from(
            [
                "session_id",
                "model",
                "tool_name",
                "tool_input",
                "agent_type",
                "last_assistant_message",
                "message",
                "permission_mode",
            ]
        ),
        json_values,
    ),
)
def test_interpret_known_events_never_raises_on_odd_types(
    event: str, payload: dict[str, JsonValue]
) -> None:
    interpret_hook(event, payload)


@pytest.mark.parametrize("event", ["Stop", "PreToolUse", "SessionEnd", "Notification", "Other"])
def test_every_effect_carries_the_native_id(event: str) -> None:
    effect = interpret_hook(event, {"session_id": "abc"})
    assert effect is not None
    assert effect.native_id == "abc"


def test_identifying_fields_are_capped() -> None:
    effect = interpret_hook(
        "SessionStart",
        {"session_id": "i" * 900, "transcript_path": "t" * 900, "model": "m" * 900},
    )
    assert effect is not None
    assert effect.native_id is not None
    assert len(effect.native_id) == 300
    assert effect.transcript_path is not None
    assert len(effect.transcript_path) == 300
    assert effect.model is not None
    assert len(effect.model) == 200
    mode = interpret_hook("UserPromptSubmit", {"permission_mode": "p" * 900})
    assert mode is not None
    assert mode.permission_mode is not None
    assert len(mode.permission_mode) == 200
