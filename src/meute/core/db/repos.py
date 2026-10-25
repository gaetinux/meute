"""Discovered repositories in the database."""

from collections.abc import Sequence
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.projects import create_project, project_by_name
from meute.core.db.rows import as_integer, as_text, fetch_all, fetch_one
from meute.core.db.task_reads import project_repo_ids
from meute.core.instants import from_db, to_db
from meute.core.project import Project, ProjectId, RepoId, name_key
from meute.core.repo import NewRepo, Repo

_text = as_text


def _row_to_repo(row: tuple[object, ...]) -> Repo:
    return Repo(
        id=RepoId(as_integer(row[0])),
        path=Path(_text(row[1])),
        name=_text(row[2]),
        kind=None if row[3] is None else _text(row[3]),
        discovered_at=from_db(_text(row[4])),
    )


def sync_repos(db: Database, found: Sequence[NewRepo]) -> list[Repo]:
    """Store `found` in one transaction and return every known repository.

    New paths are inserted with the current instant; known paths get their name
    and kind refreshed. A repository that is no longer found is never deleted.
    """
    discovered_at = to_db(db.now())
    with db.transaction() as conn:
        conn.executemany(
            "INSERT INTO repos (path, name, kind, discovered_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT (path) DO UPDATE SET name = excluded.name, kind = excluded.kind",
            [(str(repo.path), repo.name, repo.kind, discovered_at) for repo in found],
        )
    return list_repos(db)


def list_repos(db: Database) -> list[Repo]:
    """Return every repository, sorted by name ignoring case, then by path."""
    rows = fetch_all(db.conn, "SELECT id, path, name, kind, discovered_at FROM repos")
    return sorted(
        (_row_to_repo(row) for row in rows),
        key=lambda repo: (repo.name.casefold(), str(repo.path)),
    )


def get_repo(db: Database, repo_id: RepoId) -> Repo | None:
    """Return the repository `repo_id`, or None."""
    row = fetch_one(
        db.conn, "SELECT id, path, name, kind, discovered_at FROM repos WHERE id = ?", (repo_id,)
    )
    return None if row is None else _row_to_repo(row)


def link_repo(db: Database, project_id: ProjectId, repo_id: RepoId) -> None:
    """Attach a repository to a project; attaching it again changes nothing."""
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO project_repos (project_id, repo_id) VALUES (?, ?)",
            (project_id, repo_id),
        )


def move_repo(db: Database, project_id: ProjectId, repo_id: RepoId) -> None:
    """Make `project_id` the only project of a repository; doing it again changes nothing."""
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM project_repos WHERE repo_id = ? AND project_id != ?",
            (repo_id, project_id),
        )
        conn.execute(
            "INSERT OR IGNORE INTO project_repos (project_id, repo_id) VALUES (?, ?)",
            (project_id, repo_id),
        )


def unlink_repo(db: Database, project_id: ProjectId, repo_id: RepoId) -> bool:
    """Detach a repository from a project; true if there was a link to remove."""
    with db.transaction() as conn:
        cursor = conn.execute(
            "DELETE FROM project_repos WHERE project_id = ? AND repo_id = ?",
            (project_id, repo_id),
        )
    return cursor.rowcount > 0


def repo_project_links(db: Database) -> dict[RepoId, ProjectId]:
    """Return, for each linked repository, the project with the smallest identifier."""
    rows = fetch_all(db.conn, "SELECT repo_id, MIN(project_id) FROM project_repos GROUP BY repo_id")
    return {RepoId(as_integer(row[0])): ProjectId(as_integer(row[1])) for row in rows}


def create_repo_project(db: Database, name: str) -> Project:
    """Return the project `name` (by `name_key`), with every repository of that name attached.

    The project is created if needed; one of that name made meanwhile, by another window or
    a failed attempt, is reused.

    Raises:
        InvalidInput: the name is empty.
    """
    project = project_by_name(db, name) or create_project(db, name)
    key = name_key(project.name)
    for repo in list_repos(db):
        if name_key(repo.name) == key:
            link_repo(db, project.id, repo.id)
    return project


def project_repos(db: Database, project_id: ProjectId) -> list[Repo]:
    """Return the repositories attached to a project, sorted as `list_repos`."""
    linked = set(project_repo_ids(db, project_id))
    return [repo for repo in list_repos(db) if repo.id in linked]
