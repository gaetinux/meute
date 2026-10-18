"""Stopping a Claude session sends a double Ctrl-C: the fake `claude` needs both."""

import time

from conftest import Sandbox
from meute.core.db.sessions import list_sessions
from meute.core.session_state import Exited
from support import wait_until

_FAST_STOP_SECONDS = 2.0


def _new_claude(sandbox: Sandbox) -> str:
    folder = sandbox.root / "w"
    folder.mkdir(exist_ok=True)
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", "claudy")
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (session,) = list_sessions(db)
    wait_until(
        "the permission request",
        lambda: "[manual]" in sandbox.run("session", "list").stdout,
        timeout=30,
    )
    return session.id


def test_stopping_a_claude_session_takes_two_interrupts_and_is_quick(sandbox: Sandbox) -> None:
    session_id = _new_claude(sandbox)
    started = time.monotonic()
    result = sandbox.run("session", "stop", session_id[:8], "--yes")
    elapsed = time.monotonic() - started
    assert (result.returncode, result.stderr) == (0, "")
    assert elapsed < _FAST_STOP_SECONDS
    with sandbox.db() as db:
        (session,) = list_sessions(db, include_ended=True)
    assert isinstance(session.state, Exited)
