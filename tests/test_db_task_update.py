"""Versioned task updates and deletion."""

import sqlite3
from pathlib import Path

import pytest

from meute.core.actor import Author, Channel
from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.rows import fetch_all
from meute.core.db.task_notes import add_note, notes
from meute.core.db.task_update import delete_task, update_task
from meute.core.db.tasks import create_task, get_task, history
from meute.core.errors import InvalidInput, NotFound, VersionConflict
from meute.core.project import ProjectId
from meute.core.status import Blocked, Done, InProgress, Priority, Review
from meute.core.task import Task, TaskId, TaskPatch
from support import CLAUDE, FIXED, USER, at_due, date_due, new_task


def with_task(db: Database) -> Task:
    return create_task(db, new_task("Review the PR"), USER)


def test_update_bumps_version_once_and_logs_each_field(db: Database) -> None:
    t = with_task(db)
    t2 = update_task(db, t.id, 1, TaskPatch(title="New", priority=Priority.URGENT), USER)
    assert (t2.title, t2.priority, t2.version) == ("New", Priority.URGENT, 2)
    assert [e.field for e in history(db, t.id)] == ["created", "title", "priority"]


def test_event_values_use_kinds_text_and_project_name(db: Database) -> None:
    t = with_task(db)
    p = create_project(db, "meute")
    update_task(
        db,
        t.id,
        1,
        TaskPatch(status=InProgress(), due=date_due("2026-11-01"), project_id=p.id),
        CLAUDE,
    )
    update_task(
        db, t.id, 2, TaskPatch(status=Blocked(reason="waiting for CI"), project_id=None), USER
    )
    events = history(db, t.id)
    assert [(e.field, e.old_value, e.new_value) for e in events[1:]] == [
        ("status", "todo", "in_progress"),
        ("due", None, "2026-11-01"),
        ("project", None, "meute"),
        ("status", "in_progress", "blocked: waiting for CI"),
        ("project", "meute", None),
    ]
    assert (events[1].author, events[1].channel, events[1].session_id) == (
        Author.CLAUDE,
        Channel.MCP,
        "s-1",
    )


def test_stale_version_is_rejected_with_current_state_and_no_event(db: Database) -> None:
    t = with_task(db)
    update_task(db, t.id, 1, TaskPatch(title="A"), USER)
    with pytest.raises(
        VersionConflict, match=r"^modified in the meantime \(current version: 2\)$"
    ) as err:
        update_task(db, t.id, 1, TaskPatch(title="B"), CLAUDE)
    assert (err.value.current.title, err.value.current.version) == ("A", 2)
    assert len(history(db, t.id)) == 2


@pytest.mark.parametrize("patch", [TaskPatch(), TaskPatch(title=" Review the PR ")])
def test_noop_patch_changes_nothing(db: Database, patch: TaskPatch) -> None:
    t = with_task(db)
    assert update_task(db, t.id, 1, patch, USER) == t
    assert get_task(db, t.id).version == 1
    assert len(history(db, t.id)) == 1


def test_blank_title_is_rejected_and_nothing_written(db: Database) -> None:
    t = with_task(db)
    with pytest.raises(InvalidInput, match=r"^title cannot be empty$"):
        update_task(db, t.id, 1, TaskPatch(title="  ", priority=Priority.LOW), USER)
    assert get_task(db, t.id) == t
    assert len(history(db, t.id)) == 1


def test_done_sets_keeps_and_clears_completed_at(db: Database) -> None:
    t = with_task(db)
    assert update_task(db, t.id, 1, TaskPatch(status=Done()), USER).completed_at == FIXED
    kept = update_task(db, t.id, 2, TaskPatch(status=Done(), title="Renamed"), USER)
    assert kept.completed_at == FIXED
    assert update_task(db, t.id, 3, TaskPatch(status=Review()), USER).completed_at is None


def test_patch_with_unknown_project_is_not_found_and_nothing_written(db: Database) -> None:
    t = with_task(db)
    with pytest.raises(NotFound) as err:
        update_task(db, t.id, 1, TaskPatch(title="X", project_id=ProjectId(42)), USER)
    assert err.value.entity == "project"
    assert get_task(db, t.id).version == 1
    assert len(history(db, t.id)) == 1


def test_update_missing_task_is_not_found(db: Database) -> None:
    with pytest.raises(NotFound) as err:
        update_task(db, TaskId(9), 1, TaskPatch(title="X"), USER)
    assert err.value.entity == "task"


def test_two_connections_same_version_second_conflicts(tmp_path: Path) -> None:
    path = tmp_path / "meute.db"
    with (
        Database.open(path, busy_timeout_ms=1000, clock=lambda: FIXED) as a,
        Database.open(path, busy_timeout_ms=1000, clock=lambda: FIXED) as b,
    ):
        t = with_task(a)
        update_task(a, t.id, 1, TaskPatch(title="From A"), USER)
        with pytest.raises(VersionConflict) as err:
            update_task(b, t.id, 1, TaskPatch(title="From B"), CLAUDE)
        assert err.value.current.title == "From A"
        assert len(history(a, t.id)) == 2


def test_delete_checks_version_and_keeps_history(db: Database) -> None:
    t = with_task(db)
    add_note(db, t.id, "n", USER)
    with pytest.raises(VersionConflict):
        delete_task(db, t.id, 7, USER)
    delete_task(db, t.id, 1, USER)
    with pytest.raises(NotFound):
        get_task(db, t.id)
    last = history(db, t.id)[-1]
    assert (last.field, last.old_value) == ("deleted", "Review the PR")
    assert notes(db, t.id) == []


def test_task_ids_are_never_reused_after_delete(db: Database) -> None:
    create_task(db, new_task("one"), USER)
    two = create_task(db, new_task("two"), USER)
    delete_task(db, two.id, 1, USER)
    three = create_task(db, new_task("three"), USER)
    assert three.id == 3
    assert [e.field for e in history(db, two.id)] == ["created", "deleted"]


def test_stored_timestamps_are_fixed_width_utc(file_db: tuple[Database, Path]) -> None:
    db, path = file_db
    p = create_project(db, "meute")
    t = create_task(db, new_task("T", p.id), USER)
    t = update_task(db, t.id, 1, TaskPatch(due=at_due("2026-11-01T09:00[Europe/Paris]")), USER)
    add_note(db, t.id, "n", USER)
    update_task(db, t.id, 2, TaskPatch(status=Done()), USER)
    other = sqlite3.connect(path)
    try:
        queries = [
            "SELECT created_at FROM projects",
            "SELECT created_at, updated_at, completed_at, due_at FROM tasks",
            "SELECT created_at FROM task_notes",
            "SELECT created_at FROM task_events",
        ]
        values = [v for q in queries for row in fetch_all(other, q) for v in row]
    finally:
        other.close()
    assert values
    assert all(isinstance(v, str) and len(v) == 27 and v.endswith("Z") for v in values)
