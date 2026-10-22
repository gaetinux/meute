"""The last session type of each repository stays fast with many sessions."""

import time
from datetime import timedelta
from pathlib import Path
from uuid import UUID

from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, last_agent_by_repo
from meute.core.project import RepoId
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from support import FIXED

_SESSIONS = 5000
_REPOS = 50
_BOUND_SECONDS = 0.2  # generous: the suite runs in parallel


def test_five_thousand_sessions_are_answered_quickly() -> None:
    holder = [FIXED]
    with Database.in_memory(clock=lambda: holder[0]) as db:
        for index in range(_REPOS):
            _ = db.conn.execute(
                "INSERT INTO repos (path, name, kind, discovered_at) VALUES (?, ?, NULL, 'x')",
                (f"/r/{index}", f"r{index}"),
            )
        for index in range(_SESSIONS):
            holder[0] = FIXED + timedelta(seconds=index)
            agent = AgentKind.CLAUDE if index % 2 else AgentKind.BASH
            _ = create_session(
                db,
                NewSession(
                    id=SessionId(str(UUID(int=index + 1, version=4))),
                    agent=agent,
                    title="t",
                    cwd=Path("/w"),
                    state=Running(),
                    repo_id=RepoId(index % _REPOS + 1),
                ),
            )
        started = time.perf_counter()
        last = last_agent_by_repo(db)
        elapsed = time.perf_counter() - started
    assert len(last) == _REPOS
    # The last session of repository r is number 4950 + r - 1 (0-based): odd r -> Claude.
    assert last[RepoId(2)] is AgentKind.CLAUDE
    assert last[RepoId(1)] is AgentKind.BASH
    assert elapsed < _BOUND_SECONDS, f"{elapsed:.3f} s"
