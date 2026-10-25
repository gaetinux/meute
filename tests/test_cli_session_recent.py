"""End-to-end tests of `meute session recent` and `meute session resume`."""

from datetime import timedelta
from pathlib import Path

from syrupy.assertion import SnapshotAssertion

from conftest import Sandbox
from meute.core.db.claude_sessions import get_claude_details
from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, get_session, list_sessions, set_session_state
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Idle, Running
from support import FIXED, load_json, wait_until

NEWER = SessionId("aaaa1111-0000-4000-8000-000000000000")
OLDER = SessionId("bbbb2222-0000-4000-8000-000000000000")
SHELL = SessionId("cccc3333-0000-4000-8000-000000000000")
LIVE = SessionId("dddd4444-0000-4000-8000-000000000000")
OUT = SessionId("eeee5555-0000-4000-8000-000000000000")


def _seed(sandbox: Sandbox) -> None:
    """Two ended Claude sessions (3h and 2d ago), plus a Bash, a live and an expired one."""
    assert sandbox.run("config", "path").returncode == 0  # creates the database
    clock = [FIXED]
    home = sandbox.root / "home"
    with Database.open(
        sandbox.root / "data/meute/meute.db", busy_timeout_ms=1000, clock=lambda: clock[0]
    ) as db:
        rows = (
            (OLDER, AgentKind.CLAUDE, "older", home / "work", timedelta(days=-2)),
            (NEWER, AgentKind.CLAUDE, "new\x1b[31mer", Path("/srv/a\x1bb"), timedelta(hours=-3)),
            (SHELL, AgentKind.BASH, "shell", home, timedelta(hours=-1)),
            (OUT, AgentKind.CLAUDE, "expired", home, timedelta(days=-30)),
            (LIVE, AgentKind.CLAUDE, "live", home, timedelta(hours=-1)),
        )
        for session_id, agent, title, cwd, offset in rows:
            clock[0] = FIXED + offset
            _ = create_session(
                db,
                NewSession(id=session_id, agent=agent, title=title, cwd=cwd, state=Running()),
            )
            if session_id != LIVE:
                _ = set_session_state(db, session_id, Exited(code=0))
        _ = db.conn.execute("UPDATE sessions SET native_id = 'conv-1' WHERE id = ?", (OLDER,))
        _ = db.conn.execute("UPDATE sessions SET native_id = 'conv-2' WHERE id = ?", (OUT,))
        db.conn.commit()


def test_recent_text(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    _seed(sandbox)
    result = sandbox.run("session", "recent")
    assert result.returncode == 0, result.stderr
    assert result.stdout == snapshot


def test_recent_json(sandbox: Sandbox, snapshot: SnapshotAssertion) -> None:
    _seed(sandbox)
    result = sandbox.run("session", "recent", "--json")
    assert result.returncode == 0, result.stderr
    assert load_json(result.stdout.replace(str(sandbox.root), "<root>")) == snapshot


def test_recent_follows_recent_days(sandbox: Sandbox) -> None:
    _seed(sandbox)
    assert sandbox.run("config", "set", "ui.recent_days", "1").returncode == 0
    lines = sandbox.run("session", "recent").stdout.splitlines()
    assert [line.split("  ")[0] for line in lines] == [str(NEWER)[:8]]


def test_recent_without_sessions_prints_nothing(sandbox: Sandbox) -> None:
    result = sandbox.run("session", "recent")
    assert (result.returncode, result.stdout) == (0, "")
    assert load_json(sandbox.run("session", "recent", "--json").stdout) == {"sessions": []}


def _ended_claude(sandbox: Sandbox) -> SessionId:
    """A Claude session started with the fake claude that exited: native id known."""
    folder = sandbox.root / "w"
    folder.mkdir()
    env = {"MEUTE_FAKE_CLAUDE_SCRIPT": "exit"}
    result = sandbox.run("session", "new", "--cwd", str(folder), "--title", "trial", env=env)
    assert result.returncode == 0, result.stderr
    with sandbox.db() as db:
        (first,) = list_sessions(db)

    def ended() -> bool:
        with sandbox.db() as db:
            return isinstance(get_session(db, first.id).state, Exited) and (
                get_claude_details(db, first.id).native_id is not None
            )

    wait_until("the session to end", ended, timeout=30)
    return first.id


def test_resume_prints_the_resumed_session(sandbox: Sandbox) -> None:
    session_id = _ended_claude(sandbox)
    result = sandbox.run(
        "session", "resume", str(session_id)[:8], env={"MEUTE_FAKE_CLAUDE_SCRIPT": "permission"}
    )
    assert (result.returncode, result.stdout) == (0, f"Resumed: {str(session_id)[:8]} trial\n")


def test_resume_refuses_a_live_session(sandbox: Sandbox) -> None:
    session_id = _ended_claude(sandbox)
    with sandbox.db() as db:
        _ = set_session_state(db, session_id, Idle())
    result = sandbox.run("session", "resume", str(session_id)[:8])
    assert result.returncode != 0
    assert '"trial" is still running' in result.stderr


def test_resume_refuses_a_bash_session(sandbox: Sandbox) -> None:
    folder = sandbox.root / "b"
    folder.mkdir()
    assert sandbox.run("session", "new", "--kind", "bash", "--cwd", str(folder)).returncode == 0
    with sandbox.db() as db:
        (shell,) = list_sessions(db)
        _ = set_session_state(db, shell.id, Exited(code=0))
    result = sandbox.run("session", "resume", str(shell.id)[:8])
    assert result.returncode != 0
    assert "only Claude sessions resume" in result.stderr
