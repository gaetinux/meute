"""Tests for the Claude columns, session events and samples (migration 3)."""

import sqlite3
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from typing import Literal

import pytest

from meute.core.claude_session import ClaudeDetails, SessionEvent, claude_details_to_json
from meute.core.db.claude_sessions import get_claude_details, purge_samples, session_events
from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, migrate
from meute.core.db.rows import fetch_all, fetch_one
from meute.core.db.sessions import create_session
from meute.core.errors import NotFound
from meute.core.instants import to_db
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from support import FIXED

SID = SessionId("aaaa1111-0000-4000-8000-000000000000")
OTHER = SessionId("aaaa2222-0000-4000-8000-000000000000")


def make(db: Database, session_id: SessionId = SID) -> None:
    create_session(
        db,
        NewSession(
            id=session_id,
            agent=AgentKind.CLAUDE,
            title="c",
            cwd=Path("/work"),
            state=Running(),
        ),
    )


def add_event(db: Database, session_id: SessionId, event: str, minutes: int) -> None:
    db.conn.execute(
        "INSERT INTO session_events (session_id, event, detail, created_at) VALUES (?, ?, ?, ?)",
        (session_id, event, f"d-{event}", to_db(FIXED + timedelta(minutes=minutes))),
    )


def test_new_session_has_empty_details(db: Database) -> None:
    make(db)
    assert get_claude_details(db, SID) == ClaudeDetails()


def test_details_round_trip_from_raw_sql(db: Database) -> None:
    make(db)
    db.conn.execute(
        "UPDATE sessions SET native_id = 'n', transcript_path = '/t.jsonl', model = 'opus',"
        " permission_mode = 'plan', last_tool = 'Bash', pending_permission = 'Bash: ls',"
        " last_message = 'hi' WHERE id = ?",
        (SID,),
    )
    details = get_claude_details(db, SID)
    assert details == ClaudeDetails(
        native_id="n",
        transcript_path="/t.jsonl",
        model="opus",
        permission_mode="plan",
        last_tool="Bash",
        pending_permission="Bash: ls",
        last_message="hi",
    )
    assert claude_details_to_json(details) == {
        "native_id": "n",
        "transcript_path": "/t.jsonl",
        "model": "opus",
        "permission_mode": "plan",
        "last_tool": "Bash",
        "pending_permission": "Bash: ls",
        "last_message": "hi",
    }


def test_unknown_session_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound):
        get_claude_details(db, SID)


def test_events_are_ordered_oldest_first_and_limited_to_the_latest(db: Database) -> None:
    make(db)
    make(db, OTHER)
    for index, event in enumerate(["a", "b", "c", "d"]):
        add_event(db, SID, event, index)
    add_event(db, OTHER, "x", 10)
    assert [e.event for e in session_events(db, SID)] == ["a", "b", "c", "d"]
    assert session_events(db, SID, limit=2) == [
        SessionEvent(
            session_id=SID, event="c", detail="d-c", created_at=FIXED + timedelta(minutes=2)
        ),
        SessionEvent(
            session_id=SID, event="d", detail="d-d", created_at=FIXED + timedelta(minutes=3)
        ),
    ]


def add_samples(db: Database, session_id: SessionId, at_minutes: int) -> None:
    stamp = to_db(FIXED + timedelta(minutes=at_minutes))
    db.conn.execute(
        "INSERT INTO metric_samples (session_id, created_at) VALUES (?, ?)", (session_id, stamp)
    )
    db.conn.execute("INSERT INTO quota_samples (created_at) VALUES (?)", (stamp,))


def count(db: Database, table: Literal["session_events", "metric_samples", "quota_samples"]) -> int:
    row = fetch_one(db.conn, "SELECT count(*) FROM " + table)  # noqa: S608 — fixed table names
    assert row is not None
    return int(str(row[0]))


def test_deleting_a_session_deletes_its_events_and_samples(db: Database) -> None:
    make(db)
    make(db, OTHER)
    add_event(db, SID, "a", 0)
    add_event(db, OTHER, "b", 0)
    add_samples(db, SID, 0)
    add_samples(db, OTHER, 0)
    db.conn.execute("DELETE FROM sessions WHERE id = ?", (SID,))
    assert (count(db, "session_events"), count(db, "metric_samples")) == (1, 1)


def test_purge_keeps_a_sample_exactly_at_the_boundary(db: Database) -> None:
    make(db)
    for minutes in (-1, 0, 1):
        add_samples(db, SID, minutes)
    assert purge_samples(db, older_than=FIXED) == 2
    assert (count(db, "metric_samples"), count(db, "quota_samples")) == (2, 2)
    remaining = fetch_all(db.conn, "SELECT created_at FROM metric_samples ORDER BY created_at")
    assert remaining == [(to_db(FIXED),), (to_db(FIXED + timedelta(minutes=1)),)]


def test_migrating_a_v2_file_keeps_the_session_and_backs_it_up(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, MIGRATIONS[:2])
        conn.execute(
            "INSERT INTO sessions (id, agent, title, cwd, state, last_activity_at, created_at)"
            " VALUES (?, 'bash', 'keep', '/w', 'running', 'x', 'x')",
            (SID,),
        )
    with Database.open(path, busy_timeout_ms=1000) as db:
        assert db.schema_version() == 5
        assert fetch_one(db.conn, "SELECT title, model FROM sessions") == ("keep", None)
    assert (tmp_path / "meute.db.bak-2").exists()
