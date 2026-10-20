"""Reading the latest notes of every task, and the repositories of a project."""

from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.task_notes import add_note
from meute.core.db.task_reads import latest_notes, project_repo_ids
from meute.core.db.tasks import create_task
from meute.core.project import RepoId
from support import USER, new_task


def test_latest_notes_keep_the_last_two_per_task_newest_first(db: Database) -> None:
    first = create_task(db, new_task("one"), USER)
    second = create_task(db, new_task("two"), USER)
    create_task(db, new_task("three"), USER)
    for body in ("a", "b", "c"):
        add_note(db, first.id, body, USER)
    add_note(db, second.id, "only", USER)
    found = latest_notes(db)
    assert set(found) == {first.id, second.id}
    assert [n.body for n in found[first.id]] == ["c", "b"]
    assert [n.body for n in found[second.id]] == ["only"]


def test_latest_notes_honours_the_limit(db: Database) -> None:
    task = create_task(db, new_task("one"), USER)
    for body in ("a", "b", "c"):
        add_note(db, task.id, body, USER)
    assert [n.body for n in latest_notes(db, per_task=1)[task.id]] == ["c"]
    assert [n.body for n in latest_notes(db, per_task=3)[task.id]] == ["c", "b", "a"]


def test_latest_notes_of_an_empty_database(db: Database) -> None:
    assert latest_notes(db) == {}


def test_project_repo_ids(db: Database) -> None:
    project = create_project(db, "meute")
    other = create_project(db, "other")
    with db.transaction() as conn:
        for repo_id, name in ((1, "a"), (2, "b"), (3, "c")):
            conn.execute(
                "INSERT INTO repos (id, path, name, kind, discovered_at) VALUES (?, ?, ?, NULL, ?)",
                (repo_id, f"/r/{name}", name, "2026-10-14T08:30:00Z"),
            )
        for project_id, repo_id in ((project.id, 3), (project.id, 1), (other.id, 2)):
            conn.execute(
                "INSERT INTO project_repos (project_id, repo_id) VALUES (?, ?)",
                (project_id, repo_id),
            )
    assert project_repo_ids(db, project.id) == [RepoId(1), RepoId(3)]
    assert project_repo_ids(db, other.id) == [RepoId(2)]
