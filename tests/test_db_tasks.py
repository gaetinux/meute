"""Tests for task creation and listing."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from meute.core.actor import Author, Channel
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.tasks import (
    Floating,
    InProject,
    TaskFilter,
    create_task,
    get_task,
    history,
    list_tasks,
)
from meute.core.errors import InvalidInput, NotFound
from meute.core.project import ProjectId, ProjectRef
from meute.core.status import Blocked, Priority, StatusKind, Todo
from meute.core.task import NewTask, TaskId
from support import FIXED, USER, new_task


def test_create_and_get_task_with_project(db: Database) -> None:
    p = create_project(db, "meute")
    new = NewTask(title="  Write the plan ", priority=Priority.HIGH, project_id=p.id)
    t = create_task(db, new, USER)
    assert (t.title, t.version, t.status, t.priority) == (
        "Write the plan",
        1,
        Todo(),
        Priority.HIGH,
    )
    assert t.project == ProjectRef(id=p.id, name="meute")
    assert (t.created_at, t.updated_at, t.completed_at) == (FIXED, FIXED, None)
    assert get_task(db, t.id) == t
    [event] = history(db, t.id)
    assert (event.field, event.new_value, event.author, event.channel) == (
        "created",
        "Write the plan",
        Author.USER,
        Channel.CLI,
    )


def test_list_filters_done_floating_project_and_status(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    a = create_project(db, "A")
    t1, t2, t3, t4 = (
        create_task(db, new_task(n, p), USER)
        for n, p in (("t1", a.id), ("t2", None), ("t3", a.id), ("t4", None))
    )
    with closing(sqlite3.connect(path, autocommit=True)) as raw:  # no update API yet
        raw.execute(
            "UPDATE tasks SET status='done', completed_at='2026-10-14T09:00:00.000000Z' WHERE id=3"
        )
        raw.execute("UPDATE tasks SET status='blocked', blocked_reason='ci' WHERE id=4")

    def ids(task_filter: TaskFilter) -> list[TaskId]:
        return [t.id for t in list_tasks(db, task_filter)]

    assert ids(TaskFilter()) == [t1.id, t2.id, t4.id]
    assert ids(TaskFilter(project=Floating())) == [t2.id, t4.id]
    assert ids(TaskFilter(include_done=True, project=InProject(project_id=a.id))) == [t1.id, t3.id]
    assert ids(TaskFilter(status=StatusKind.DONE)) == [t3.id]
    assert ids(TaskFilter(status=StatusKind.BLOCKED)) == [t4.id]
    assert get_task(db, t4.id).status == Blocked(reason="ci")


def test_get_missing_task_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound, match=r"^task not found: #99$"):
        get_task(db, TaskId(99))


def test_create_with_unknown_project_is_not_found_and_creates_nothing(db: Database) -> None:
    with pytest.raises(NotFound, match=r"^project not found: 42$") as info:
        create_task(db, new_task("x", ProjectId(42)), USER)
    assert info.value.entity == "project"
    assert info.value.ident == "42"
    assert list_tasks(db, TaskFilter(include_done=True)) == []


def test_blank_title_is_rejected(db: Database) -> None:
    with pytest.raises(InvalidInput, match=r"^title cannot be empty$"):
        create_task(db, new_task("   "), USER)
    assert list_tasks(db, TaskFilter(include_done=True)) == []


def test_create_task_only_maps_foreign_key_violations(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    p = create_project(db, "p")
    with closing(sqlite3.connect(path, autocommit=True)) as raw:
        raw.execute(
            "CREATE TRIGGER refuse BEFORE INSERT ON tasks BEGIN SELECT RAISE(ABORT, 'refused'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        create_task(db, new_task("x", p.id), USER)
