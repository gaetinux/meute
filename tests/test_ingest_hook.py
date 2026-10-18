"""`meute ingest hook <Event>`: never disturbs Claude, records what it can."""

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from conftest import Sandbox
from meute.core.db.claude_sessions import get_claude_details, session_events
from meute.core.db.sessions import create_session, get_session
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Idle, PermissionRequested, Unknown

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
FIXTURES = Path(__file__).parent / "fixtures/claude/2.1.302/hooks"


def payload(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text(encoding="utf-8")


def ingest(
    box: Sandbox, event: str, stdin: str, *, session: str | None = str(SID)
) -> CompletedProcess[str]:
    env = {} if session is None else {"MEUTE_SESSION": session}
    return box.run("ingest", "hook", event, env=env, stdin=stdin)


def log_text(box: Sandbox) -> str:
    log = box.root / "state/meute/ingest.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


@pytest.fixture
def seeded(sandbox: Sandbox) -> Sandbox:
    with sandbox.db() as db:
        create_session(
            db,
            NewSession(
                id=SID, agent=AgentKind.CLAUDE, title="c", cwd=Path("/work"), state=Unknown()
            ),
        )
    return sandbox


def test_hook_updates_the_session(seeded: Sandbox) -> None:
    start = ingest(seeded, "SessionStart", payload("SessionStart-1"))
    permission = ingest(seeded, "PermissionRequest", payload("PermissionRequest-1"))
    for result in (start, permission):
        assert (result.returncode, result.stdout) == (0, "")
    with seeded.db() as db:
        assert get_session(db, SID).state == PermissionRequested()
        assert get_claude_details(db, SID).pending_permission is not None
    assert log_text(seeded) == ""


@pytest.mark.parametrize("session", [None, "not-a-uuid", "bbbb1111-0000-4000-8000-000000000000"])
def test_unknown_or_missing_session_is_ignored_silently(
    seeded: Sandbox, session: str | None
) -> None:
    result = ingest(seeded, "Stop", payload("Stop-1"), session=session)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert log_text(seeded) == ""
    with seeded.db() as db:
        assert get_session(db, SID).state == Unknown()


def test_missing_database_is_ignored_silently(sandbox: Sandbox) -> None:
    result = ingest(sandbox, "Stop", payload("Stop-1"))
    assert (result.returncode, result.stdout) == (0, "")
    assert not (sandbox.root / "data/meute/meute.db").exists()
    assert log_text(sandbox) == ""


@pytest.mark.parametrize(
    "stdin",
    [
        pytest.param("{not json", id="broken"),
        pytest.param("[1, 2]", id="array"),
        pytest.param('"text"', id="string"),
        pytest.param("null", id="null"),
        pytest.param("", id="empty"),
        pytest.param("x" * 2_000_000, id="oversized"),
        pytest.param('{"session_id": "\\ud800"}', id="surrogate"),
    ],
)
def test_bad_input_is_logged_and_exits_zero(seeded: Sandbox, stdin: str) -> None:
    result = ingest(seeded, "Stop", stdin)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert log_text(seeded).count("\n") == 1
    with seeded.db() as db:
        assert get_session(db, SID).state == Unknown()


def test_blank_session_id_does_not_block_later_hooks(seeded: Sandbox) -> None:
    ingest(seeded, "Notification", '{"session_id": "  "}')
    ingest(seeded, "SessionStart", payload("SessionStart-1"))
    with seeded.db() as db:
        assert get_session(db, SID).state == Idle()


def test_locked_database_drops_the_event_within_the_budget(seeded: Sandbox) -> None:
    holder = sqlite3.connect(seeded.root / "data/meute/meute.db", autocommit=True)
    try:
        holder.execute("BEGIN IMMEDIATE")
        started = time.monotonic()
        result = ingest(seeded, "PreToolUse", payload("PreToolUse-1"))
        elapsed = time.monotonic() - started
    finally:
        holder.execute("ROLLBACK")
        holder.close()
    assert elapsed < 1
    assert (result.returncode, result.stdout) == (0, "")
    assert "OperationalError" in log_text(seeded)
    with seeded.db() as db:
        assert get_session(db, SID).state == Unknown()
        assert session_events(db, SID) == []


def test_old_schema_is_never_migrated_from_ingest(seeded: Sandbox) -> None:
    path = seeded.root / "data/meute/meute.db"
    with sqlite3.connect(path, autocommit=True) as conn:
        conn.execute("PRAGMA user_version = 2")
    result = ingest(seeded, "Stop", payload("Stop-1"))
    assert (result.returncode, result.stdout) == (0, "")
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA user_version").fetchone() == (2,)
        assert conn.execute("SELECT count(*) FROM session_events").fetchone() == (0,)
    assert "MigrationError" in log_text(seeded)


def test_parallel_hooks_all_land_or_are_logged(seeded: Sandbox) -> None:
    body = payload("PreToolUse-1")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(ingest, seeded, "PreToolUse", body) for _ in range(8)]
        results = [future.result() for future in futures]
    assert all((r.returncode, r.stdout) == (0, "") for r in results)
    with seeded.db() as db:
        landed = len(session_events(db, SID))
        assert db.pragma("integrity_check") == "ok"
    logged = log_text(seeded).count("\n")
    assert landed + logged >= 8


def test_lone_surrogate_in_a_field_is_logged_not_fatal(seeded: Sandbox) -> None:
    body = json.dumps({"session_id": "s", "tool_name": "Bash\ud800"}, ensure_ascii=True)
    result = ingest(seeded, "PreToolUse", body)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    assert log_text(seeded).count("\n") <= 1
