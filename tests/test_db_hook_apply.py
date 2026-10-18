"""Applying an interpreted hook to the database."""

from datetime import timedelta
from pathlib import Path

import pytest

from meute.core.db.claude_sessions import get_claude_details, session_events
from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.db.sessions import create_session, get_session, set_session_state
from meute.core.errors import NotFound
from meute.core.hooks import HookEffect, interpret_hook
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import (
    Exited,
    Idle,
    PermissionRequested,
    Running,
    SessionState,
    SubagentRunning,
    Unreachable,
    WaitingInput,
)
from support import FIXED, claude_fixture

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
NATIVE = "7393e221-2a26-44ab-ae9c-fc905efac6e6"


def make(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/work"), state=Idle()),
    )


def hook(db: Database, event: str, payload: str) -> bool:
    effect = interpret_hook(event, claude_fixture(payload))
    assert effect is not None
    return apply_hook(db, SID, event, effect)


def test_permission_then_post_tool_clears_pending(db: Database) -> None:
    make(db)
    assert hook(db, "PermissionRequest", "PermissionRequest-1")
    assert get_session(db, SID).state == PermissionRequested()
    assert get_claude_details(db, SID).pending_permission == "Bash mkdir /tmp/capture/denied"
    assert hook(db, "PostToolUse", "PostToolUse-1")
    assert get_session(db, SID).state == Running()
    assert get_claude_details(db, SID).pending_permission is None


def test_session_start_records_claude_columns_and_history(db: Database) -> None:
    make(db)
    hook(db, "SessionStart", "SessionStart-1")
    details = get_claude_details(db, SID)
    assert details.native_id == NATIVE
    assert details.model == "claude-opus-5-5"
    assert [e.event for e in session_events(db, SID)] == ["SessionStart"]


def test_return_value_tells_whether_state_changed(db: Database) -> None:
    make(db)
    assert hook(db, "PreToolUse", "PreToolUse-1")
    assert not hook(db, "PreToolUse", "PreToolUse-1")  # already Running
    assert get_claude_details(db, SID).last_tool == "Bash echo meute-capture"


def test_late_hook_after_session_end_changes_nothing_but_history(db: Database) -> None:
    make(db)
    hook(db, "SessionEnd", "SessionEnd-1")
    before = get_session(db, SID)
    assert before.state == Exited(code=None)
    assert before.ended_at == FIXED
    assert not hook(db, "Stop", "Stop-1")
    after = get_session(db, SID)
    assert after == before
    assert get_claude_details(db, SID).last_message is None
    assert [e.event for e in session_events(db, SID)] == ["SessionEnd", "Stop"]


def test_hook_of_unreachable_session_is_history_only(db: Database) -> None:
    make(db)
    set_session_state(db, SID, Unreachable())
    assert not hook(db, "PreToolUse", "PreToolUse-1")
    assert get_session(db, SID).state == Unreachable()
    assert get_claude_details(db, SID).last_tool is None
    assert [e.event for e in session_events(db, SID)] == ["PreToolUse"]


def test_mismatched_native_id_is_history_only(db: Database) -> None:
    make(db)
    hook(db, "SessionStart", "SessionStart-1")
    other = HookEffect(state=Running(), native_id="other-native", model="m", history="")
    assert not apply_hook(db, SID, "SessionStart", other)
    assert get_session(db, SID).state == Idle()
    assert get_claude_details(db, SID).model == "claude-opus-5-5"
    assert len(session_events(db, SID)) == 2


def test_matching_native_id_is_applied(db: Database) -> None:
    make(db)
    hook(db, "SessionStart", "SessionStart-1")
    effect = HookEffect(state=Running(), native_id=NATIVE, history="")
    assert apply_hook(db, SID, "SessionStart", effect)


def test_last_activity_moves_on_each_applied_hook(db: Database) -> None:
    make(db)
    moments = iter(FIXED + timedelta(minutes=n) for n in range(1, 5))
    object.__setattr__(db, "clock", lambda: next(moments))
    hook(db, "PreToolUse", "PreToolUse-1")
    first = get_session(db, SID).last_activity_at
    notify = HookEffect(state=None, history="hi")
    apply_hook(db, SID, "Notification", notify)
    second = get_session(db, SID).last_activity_at
    assert first < second


def test_stateless_hook_keeps_pending_permission(db: Database) -> None:
    make(db)
    hook(db, "PermissionRequest", "PermissionRequest-1")
    apply_hook(db, SID, "Notification", HookEffect(state=None, history="n"))
    assert get_claude_details(db, SID).pending_permission is not None
    assert get_session(db, SID).state == PermissionRequested()


def test_stop_records_message(db: Database) -> None:
    make(db)
    hook(db, "Stop", "Stop-2")
    assert get_session(db, SID).state == WaitingInput()
    assert get_claude_details(db, SID).last_message == "La commande a affiché `meute-capture`."


def test_unknown_session_raises(db: Database) -> None:
    with pytest.raises(NotFound):
        apply_hook(db, SID, "Stop", HookEffect(state=None, history=""))
    assert not db.conn.in_transaction


def test_late_subagent_stop_keeps_waiting_input(db: Database) -> None:
    # S7: a background subagent stops after the turn's Stop.
    make(db)
    hook(db, "Stop", "Stop-4")
    assert not hook(db, "SubagentStop", "SubagentStop-1")
    assert get_session(db, SID).state == WaitingInput()
    assert [e.event for e in session_events(db, SID)] == ["Stop", "SubagentStop"]


def test_late_subagent_stop_keeps_idle(db: Database) -> None:
    make(db)
    assert not hook(db, "SubagentStop", "SubagentStop-1")
    assert get_session(db, SID).state == Idle()


@pytest.mark.parametrize("state", [Running(), SubagentRunning()])
def test_subagent_stop_while_working_gives_running(db: Database, state: SessionState) -> None:
    make(db)
    set_session_state(db, SID, state)
    assert hook(db, "SubagentStop", "SubagentStop-1") == (state != Running())
    assert get_session(db, SID).state == Running()


def test_stop_of_another_claude_session_is_history_only(db: Database) -> None:
    make(db)
    hook(db, "SessionStart", "SessionStart-1")  # records 7393e221...
    set_session_state(db, SID, Running())
    stop = interpret_hook("Stop", {**claude_fixture("Stop-1"), "session_id": "foreign"})
    assert stop is not None
    assert not apply_hook(db, SID, "Stop", stop)
    assert get_session(db, SID).state == Running()
    assert get_claude_details(db, SID).last_message is None


def test_first_hook_records_native_id(db: Database) -> None:
    make(db)
    hook(db, "Stop", "Stop-1")
    assert get_claude_details(db, SID).native_id == NATIVE
