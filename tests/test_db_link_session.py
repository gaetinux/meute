"""`link_session_task`."""

from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.sessions import create_session, get_session, link_session_task
from meute.core.db.tasks import create_task
from meute.core.errors import NotFound
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Running
from meute.core.task import TaskId
from support import USER, new_task

SESSION = SessionId("aaaa1111-0000-4000-8000-000000000000")


def _session(db: Database) -> None:
    create_session(
        db,
        NewSession(id=SESSION, agent=AgentKind.BASH, title="s", cwd=Path("/work"), state=Running()),
    )


def test_link_sets_the_task(db: Database) -> None:
    _session(db)
    task = create_task(db, new_task("t"), USER)
    assert link_session_task(db, SESSION, task.id).task_id == task.id
    assert get_session(db, SESSION).task_id == task.id


def test_link_unknown_task_changes_nothing(db: Database) -> None:
    _session(db)
    with pytest.raises(NotFound):
        link_session_task(db, SESSION, TaskId(99))
    assert get_session(db, SESSION).task_id is None


def test_link_unknown_session(db: Database) -> None:
    task = create_task(db, new_task("t"), USER)
    with pytest.raises(NotFound):
        link_session_task(db, SessionId("zzzz"), task.id)
