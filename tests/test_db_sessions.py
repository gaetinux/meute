"""Tests for the sessions table and its access functions."""

import os
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, migrate
from meute.core.db.projects import create_project
from meute.core.db.rows import fetch_one, inserted_id
from meute.core.db.sessions import (
    create_session,
    find_session,
    get_session,
    list_sessions,
    set_session_state,
)
from meute.core.db.tasks import create_task
from meute.core.errors import InvalidInput, NotFound
from meute.core.project import ProjectId, RepoId
from meute.core.session import AgentKind, NewSession, SessionId
from meute.core.session_state import Exited, Idle, Running, Unreachable
from meute.core.task import TaskId
from support import FIXED, USER, new_task

FIRST = SessionId("aaaa1111-0000-4000-8000-000000000000")
SECOND = SessionId("aaaa2222-0000-4000-8000-000000000000")


def new_bash(session_id: SessionId = FIRST, title: str = "shell") -> NewSession:
    return NewSession(
        id=session_id, agent=AgentKind.BASH, title=title, cwd=Path("/work"), state=Running()
    )


def test_create_then_get_round_trips_every_field(db: Database) -> None:
    project = create_project(db, "meute")
    task = create_task(db, new_task("write", project.id), USER)
    cursor = db.conn.execute(
        "INSERT INTO repos (path, name, kind, discovered_at) VALUES ('/r', 'r', NULL, 'x')"
    )
    repo_id = RepoId(inserted_id(cursor))
    created = create_session(
        db,
        NewSession(
            id=FIRST,
            agent=AgentKind.CLAUDE,
            title="work",
            cwd=Path("/work/repo"),
            state=Exited(code=3),
            project_id=project.id,
            repo_id=repo_id,
            task_id=task.id,
        ),
    )
    assert created.id == FIRST
    assert created.agent is AgentKind.CLAUDE
    assert created.title == "work"
    assert created.project_id == project.id
    assert created.repo_id == repo_id
    assert created.task_id == task.id
    assert created.cwd == Path("/work/repo")
    assert created.state == Exited(code=3)
    assert created.created_at == created.last_activity_at == FIXED
    assert created.ended_at is None
    assert get_session(db, FIRST) == created


def test_create_strips_title_and_refuses_empty(db: Database) -> None:
    assert create_session(db, new_bash(title="  shell \n")).title == "shell"
    with pytest.raises(InvalidInput, match=r"^title cannot be empty$"):
        create_session(db, new_bash(SECOND, title="  "))


def test_create_refuses_non_utf8_cwd(db: Database) -> None:
    cwd = Path(os.fsdecode(b"/tmp/\xff"))
    new = NewSession(id=FIRST, agent=AgentKind.BASH, title="t", cwd=cwd, state=Running())
    with pytest.raises(InvalidInput, match=r"^path is not valid UTF-8: "):
        create_session(db, new)


def test_list_excludes_ended_unless_asked(db: Database) -> None:
    create_session(db, new_bash(FIRST))
    create_session(db, new_bash(SECOND))
    set_session_state(db, SECOND, Exited(code=0))
    assert [s.id for s in list_sessions(db)] == [FIRST]
    assert [s.id for s in list_sessions(db, include_ended=True)] == [FIRST, SECOND]


def test_ended_at_is_set_once_when_leaving_live_states() -> None:
    t0 = FIXED
    t1, t2, t3 = t0 + timedelta(hours=1), t0 + timedelta(hours=2), t0 + timedelta(hours=3)
    holder: list[datetime] = [t0]
    with Database.in_memory(clock=lambda: holder[0]) as db:
        create_session(db, new_bash())
        holder[0] = t1
        idle = set_session_state(db, FIRST, Idle())
        assert (idle.ended_at, idle.last_activity_at) == (None, t1)
        holder[0] = t2
        exited = set_session_state(db, FIRST, Exited(code=2))
        assert (exited.ended_at, exited.last_activity_at) == (t2, t2)
        holder[0] = t3
        gone = set_session_state(db, FIRST, Unreachable())
        assert (gone.ended_at, gone.last_activity_at) == (t2, t3)
        assert gone.state == Unreachable()


def test_set_state_of_missing_session_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound, match=r"^session not found: "):
        set_session_state(db, FIRST, Idle())


def test_get_missing_session_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound, match=r"^session not found: "):
        get_session(db, FIRST)


def test_find_session_by_unique_prefix_ambiguous_and_short(db: Database) -> None:
    create_session(db, new_bash(FIRST))
    create_session(db, new_bash(SECOND))
    assert find_session(db, "aaaa1").id == FIRST
    assert find_session(db, "AAAA1").id == FIRST
    assert find_session(db, FIRST).id == FIRST
    with pytest.raises(InvalidInput, match=r"^ambiguous session id: aaaa$"):
        find_session(db, "aaaa")
    with pytest.raises(NotFound, match=r"^session not found: aaa$"):
        find_session(db, "aaa")


def test_find_session_prefix_is_not_a_pattern(db: Database) -> None:
    create_session(db, new_bash(FIRST))
    for prefix in ("%%%%", "____", "aaa%"):
        with pytest.raises(NotFound):
            find_session(db, prefix)


def test_data_version_changes_after_a_write_from_another_connection(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000) as db:
        before = db.data_version()
        with Database.open(path, busy_timeout_ms=1000) as other:
            create_session(other, new_bash())
        assert db.data_version() != before


def test_migrating_a_v1_file_keeps_tasks_and_backs_it_up(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        migrate(conn, path, MIGRATIONS[:1])
        conn.execute(
            "INSERT INTO tasks (title, status, priority, version, created_at, updated_at)"
            " VALUES ('keep me', 'todo', 'normal', 1, 'x', 'x')"
        )
    with Database.open(path, busy_timeout_ms=1000) as db:
        assert db.schema_version() == 4
        assert fetch_one(db.conn, "SELECT title FROM tasks") == ("keep me",)
    assert (tmp_path / "meute.db.bak-1").exists()


@pytest.mark.parametrize(
    ("entity", "references"),
    [
        ("project", {"project_id": ProjectId(42)}),
        ("repository", {"repo_id": RepoId(42)}),
        ("task", {"task_id": TaskId(42)}),
    ],
)
def test_create_with_missing_reference_is_not_found(
    db: Database, entity: str, references: dict[str, int]
) -> None:
    new = replace(new_bash(), **references)
    with pytest.raises(NotFound, match=rf"^{entity} not found: 42$"):
        create_session(db, new)
    assert list_sessions(db, include_ended=True) == []
