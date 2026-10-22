"""Tests for the project each repository is linked to."""

from datetime import UTC, datetime
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.projects import create_project
from meute.core.db.repos import link_repo, repo_project_links, sync_repos
from meute.core.project import ProjectId, ProjectRef, RepoId
from meute.core.repo import NewRepo, Repo
from meute.core.session_project import repo_projects


def test_no_link_gives_an_empty_mapping(db: Database) -> None:
    assert repo_project_links(db) == {}


def test_smallest_project_id_wins_per_repository(db: Database) -> None:
    (repo,) = sync_repos(db, [NewRepo(path=Path("/g/a"), name="a", kind=None)])
    first = create_project(db, "first")
    second = create_project(db, "second")
    link_repo(db, second.id, repo.id)
    link_repo(db, first.id, repo.id)
    assert repo_project_links(db) == {repo.id: first.id}


def _repo(repo_id: int, name: str) -> Repo:
    return Repo(
        id=RepoId(repo_id),
        path=Path("/g") / name,
        name=name,
        kind=None,
        discovered_at=datetime(2026, 10, 1, tzinfo=UTC),
    )


def test_name_fallback_fills_unlinked_repositories() -> None:
    refs = (ProjectRef(id=ProjectId(1), name="Meute"), ProjectRef(id=ProjectId(2), name="x"))
    result = repo_projects(
        {RepoId(2): ProjectId(2)}, (_repo(1, "meute"), _repo(2, "other"), _repo(3, "nothing")), refs
    )
    assert result == {RepoId(1): ProjectId(1), RepoId(2): ProjectId(2)}
