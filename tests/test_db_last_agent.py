"""The last session type of each repository, read from the database."""

from datetime import datetime, timedelta
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, last_agent_by_repo
from meute.core.project import RepoId
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from support import FIXED

_ONE = SessionId("aaaa1111-0000-4000-8000-000000000000")
_TWO = SessionId("aaaa2222-0000-4000-8000-000000000000")
_THREE = SessionId("aaaa3333-0000-4000-8000-000000000000")
_FOUR = SessionId("aaaa4444-0000-4000-8000-000000000000")


def _repo(db: Database, name: str) -> RepoId:
    cursor = db.conn.execute(
        "INSERT INTO repos (path, name, kind, discovered_at) VALUES (?, ?, NULL, 'x')",
        (f"/r/{name}", name),
    )
    assert cursor.lastrowid is not None
    return RepoId(cursor.lastrowid)


def _new(session_id: SessionId, agent: AgentKind, repo_id: RepoId | None) -> NewSession:
    return NewSession(
        id=session_id,
        agent=agent,
        title="t",
        cwd=Path("/w"),
        state=Running(),
        repo_id=repo_id,
    )


def test_no_session_means_no_entry(db: Database) -> None:
    assert last_agent_by_repo(db) == {}


def test_the_most_recent_session_of_each_repository_wins() -> None:
    holder: list[datetime] = [FIXED]
    with Database.in_memory(clock=lambda: holder[0]) as db:
        first, second = _repo(db, "a"), _repo(db, "b")
        create_session(db, _new(_ONE, AgentKind.BASH, first))
        create_session(db, _new(_TWO, AgentKind.CLAUDE, second))
        holder[0] = FIXED + timedelta(hours=1)
        create_session(db, _new(_THREE, AgentKind.CLAUDE, first))
        create_session(db, _new(_FOUR, AgentKind.BASH, None))  # no repository: ignored
        assert last_agent_by_repo(db) == {first: AgentKind.CLAUDE, second: AgentKind.CLAUDE}


def test_ended_sessions_count_too() -> None:
    with Database.in_memory(clock=lambda: FIXED) as db:
        repo = _repo(db, "a")
        create_session(db, _new(_ONE, AgentKind.CLAUDE, repo))
        created = create_session(db, _new(_TWO, AgentKind.BASH, repo))
        assert created.state == Running()
        db.conn.execute("UPDATE sessions SET state = 'exited', exit_code = 0 WHERE id = ?", (_TWO,))
        assert last_agent_by_repo(db) == {repo: AgentKind.BASH}


def test_equal_creation_instants_are_settled_by_the_larger_id() -> None:
    with Database.in_memory(clock=lambda: FIXED) as db:
        repo = _repo(db, "a")
        create_session(db, _new(_TWO, AgentKind.BASH, repo))
        create_session(db, _new(_ONE, AgentKind.CLAUDE, repo))
        assert last_agent_by_repo(db) == {repo: AgentKind.BASH}
        create_session(db, _new(_THREE, AgentKind.CLAUDE, repo))
        assert last_agent_by_repo(db) == {repo: AgentKind.CLAUDE}
