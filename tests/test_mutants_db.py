"""Tests added after mutmut: database behaviour that earlier tests left unchecked."""

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meute.core.db import connection
from meute.core.db.connection import Database
from meute.core.db.migrations import MIGRATIONS, _load_migrations  # pyright: ignore[reportPrivateUsage] — the loader runs once at import, so only a direct call sees a mutant
from meute.core.db.projects import create_project, project_by_name
from meute.core.db.rows import fetch_all, row_to_event, row_to_note, row_to_project
from meute.core.db.task_notes import add_note, notes
from meute.core.db.task_update import diff_tasks, update_task
from meute.core.db.tasks import create_task, get_task, history
from meute.core.errors import InvalidInput, NotFound
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.task import NewTask, TaskPatch
from support import FIXED, USER, at_due, date_due, new_task


def test_migration_files_are_loaded_in_order_as_sql_text() -> None:
    assert _load_migrations() == MIGRATIONS
    assert len(MIGRATIONS) >= 1
    assert MIGRATIONS[0].lstrip().startswith("CREATE TABLE projects")


def test_open_creates_missing_parent_folders(tmp_path: Path) -> None:
    path = tmp_path / "a" / "b" / "meute.db"
    with Database.open(path, busy_timeout_ms=1000):
        assert path.is_file()


def test_connections_commit_each_statement_themselves(
    file_db: tuple[Database, Path], db: Database
) -> None:
    assert file_db[0].conn.autocommit is True
    assert db.conn.autocommit is True


def test_open_hands_its_path_to_the_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Path | None] = []

    def spy(_conn: sqlite3.Connection, db_path: Path | None) -> None:
        seen.append(db_path)

    monkeypatch.setattr(connection, "migrate", spy)
    path = tmp_path / "meute.db"
    with Database.open(path, busy_timeout_ms=1000):
        pass
    assert seen == [path]


@pytest.mark.parametrize("name", ["", "user version", "user_version;", "USER_VERSION"])
def test_pragma_rejects_bad_names_with_a_message(db: Database, name: str) -> None:
    with pytest.raises(InvalidInput, match=f"invalid pragma name: {name!r}"):
        db.pragma(name)


def test_project_description_defaults_to_empty_and_keeps_all_columns(db: Database) -> None:
    assert create_project(db, "meute").description == ""
    db.conn.execute("UPDATE projects SET instructions = 'follow TDD'")
    created = create_project(db, "other", "the description")
    found = project_by_name(db, "other")
    assert found == created
    assert found is not None
    assert (found.description, found.instructions, found.created_at) == (
        "the description",
        "",
        FIXED,
    )
    first = project_by_name(db, "meute")
    assert first is not None
    assert (first.description, first.instructions) == ("", "follow TDD")


def test_empty_project_name_message(db: Database) -> None:
    with pytest.raises(InvalidInput, match=r"^project name cannot be empty$"):
        create_project(db, "  ")


def test_task_created_with_a_due_stores_it(db: Database) -> None:
    dated = create_task(db, NewTask(title="a", due=date_due("2026-10-20")), USER)
    timed = create_task(db, NewTask(title="b", due=at_due("2026-10-20T09:00[Europe/Paris]")), USER)
    assert get_task(db, dated.id).due == date_due("2026-10-20")
    assert get_task(db, timed.id).due == at_due("2026-10-20T09:00[Europe/Paris]")


def test_title_update_keeps_the_project_and_logs_only_the_title(db: Database) -> None:
    project = create_project(db, "meute")
    task = create_task(db, new_task("old", project.id), USER)
    updated = update_task(db, task.id, 1, TaskPatch(title="new"), USER)
    assert updated.project == ProjectRef(id=project.id, name="meute")
    assert [event.field for event in history(db, task.id)][1:] == ["title"]


def test_description_update_is_recorded_under_its_name(db: Database) -> None:
    task = create_task(db, new_task("t"), USER)
    update_task(db, task.id, 1, TaskPatch(description="more"), USER)
    assert [(e.field, e.old_value, e.new_value) for e in history(db, task.id)][-1] == (
        "description",
        "",
        "more",
    )
    assert diff_tasks(task, replace(task, description="x")) == [("description", "", "x")]


def test_moving_to_an_unknown_project_names_it(db: Database) -> None:
    task = create_task(db, new_task("t"), USER)
    with pytest.raises(NotFound, match="project not found: 999"):
        update_task(db, task.id, 1, TaskPatch(project_id=ProjectId(999)), USER)


def test_corrupt_rows_say_what_was_expected() -> None:
    with pytest.raises(ValueError, match="corrupt row: expected text, got 5"):
        row_to_project((1, 5, "", "", "2026-10-14T08:30:00.000000Z"))
    with pytest.raises(ValueError, match="corrupt row: expected integer, got 'x'"):
        row_to_project(("x", "n", "", "", "2026-10-14T08:30:00.000000Z"))


def test_task_row_reads_every_column_from_its_own_position(db: Database) -> None:
    db.conn.execute("INSERT INTO repos (id, path, name, discovered_at) VALUES (7, '/r', 'r', 'x')")
    task = create_task(db, new_task("t"), USER)
    db.conn.execute("UPDATE tasks SET repo_id = 7, updated_at = '2026-10-15T09:00:00.000000Z'")
    loaded = get_task(db, task.id)
    assert loaded.repo_id == RepoId(7)
    assert loaded.created_at == FIXED
    assert loaded.updated_at == datetime(2026, 10, 15, 9, 0, tzinfo=UTC)
    assert loaded.version == 1


def test_event_row_keeps_task_id_and_instant(db: Database) -> None:
    task = create_task(db, new_task("t"), USER)
    (event,) = history(db, task.id)
    assert event.task_id == task.id
    assert event.created_at == FIXED
    rows = fetch_all(
        db.conn,
        "SELECT task_id, field, old_value, new_value, author, channel,"
        " session_id, created_at FROM task_events",
    )
    assert row_to_event(rows[0]) == event


def test_note_row_keeps_its_own_id(db: Database) -> None:
    first = create_task(db, new_task("first"), USER)
    second = create_task(db, new_task("second"), USER)
    add_note(db, first.id, "a", USER)
    add_note(db, first.id, "b", USER)
    added = add_note(db, second.id, "c", USER)
    assert added.id == 3
    (read,) = notes(db, second.id)
    assert (read.id, read.task_id) == (3, second.id)
    row = fetch_all(
        db.conn,
        "SELECT id, task_id, body, author, channel, session_id, created_at"
        " FROM task_notes WHERE id = 3",
    )[0]
    assert row_to_note(row) == read
