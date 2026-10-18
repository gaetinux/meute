"""`/clear`, `/resume` and `/compact`: the Claude session goes on, meute's session is not over.

The `clear` and `resume` payloads are per Claude Code docs, not captured (ruling R20): to check
in the plan-4 manual trial. The `compact` one is the captured `SessionStart-2`.
"""

from collections.abc import Mapping
from pathlib import Path

import pytest

from meute.core.db.claude_sessions import get_claude_details, session_events
from meute.core.db.connection import Database
from meute.core.db.hook_apply import apply_hook
from meute.core.db.sessions import create_session, get_session
from meute.core.hooks import interpret_hook
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Compacting, Exited, Idle, Running
from support import claude_fixture

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
FIRST = "7393e221-2a26-44ab-ae9c-fc905efac6e6"
SECOND = "0b4d6a39-2f7e-4a7c-9c1e-5d2b8f3e6a10"


def _make(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/w"), state=Running()),
    )


def _hook(db: Database, event: str, payload: Mapping[str, object]) -> bool:
    effect = interpret_hook(event, payload)
    assert effect is not None
    return apply_hook(db, SID, event, effect)


@pytest.mark.parametrize("reason", ["clear", "resume"])
def test_session_end_on_clear_or_resume_is_history_only(reason: str) -> None:
    # per Claude Code docs, not captured
    effect = interpret_hook("SessionEnd", {"session_id": FIRST, "reason": reason})
    assert effect is not None
    assert effect.state is None
    assert effect.history == reason


def test_session_end_for_another_reason_still_exits() -> None:
    effect = interpret_hook("SessionEnd", {"session_id": FIRST, "reason": "logout"})
    assert effect is not None
    assert effect.state == Exited(code=None)


def test_session_start_after_compact_keeps_the_state(db: Database) -> None:
    _make(db)
    _ = _hook(db, "SessionStart", claude_fixture("SessionStart-1"))
    _ = _hook(db, "PreCompact", {"session_id": FIRST})
    assert not _hook(db, "SessionStart", claude_fixture("SessionStart-2"))
    assert get_session(db, SID).state == Compacting()
    assert [e.event for e in session_events(db, SID)][-1] == "SessionStart"


@pytest.mark.parametrize("source", ["clear", "resume"])
def test_clear_or_resume_rebinds_the_native_id(db: Database, source: str) -> None:
    _make(db)
    _ = _hook(db, "SessionStart", {"session_id": FIRST, "source": "startup"})
    # per Claude Code docs, not captured: SessionEnd of the old id, SessionStart of the new one
    _ = _hook(db, "SessionEnd", {"session_id": FIRST, "reason": source})
    assert get_session(db, SID).state == Idle()
    _ = _hook(db, "SessionStart", {"session_id": SECOND, "source": source})
    assert get_claude_details(db, SID).native_id == SECOND
    assert get_session(db, SID).state == Idle()
    _ = _hook(db, "UserPromptSubmit", {"session_id": SECOND})
    assert get_session(db, SID).state == Running()
    _ = _hook(db, "Stop", {"session_id": FIRST})  # the old id is no longer ours
    assert get_session(db, SID).state == Running()


def test_startup_with_another_id_is_still_refused(db: Database) -> None:
    _make(db)
    _ = _hook(db, "SessionStart", {"session_id": FIRST, "source": "startup"})
    assert not _hook(db, "SessionStart", {"session_id": SECOND, "source": "startup"})
    assert get_claude_details(db, SID).native_id == FIRST
