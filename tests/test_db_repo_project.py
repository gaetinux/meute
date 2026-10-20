"""Linking repositories to projects, and the project made from a repository's name."""

from pathlib import Path

import pytest

from meute.core.db.connection import Database
from meute.core.db.projects import create_project, list_projects
from meute.core.db.repos import create_repo_project, link_repo, sync_repos
from meute.core.db.task_reads import project_repo_ids
from meute.core.errors import InvalidInput
from meute.core.repo import NewRepo


def _repo(path: str, name: str) -> NewRepo:
    return NewRepo(path=Path(path), name=name, kind=None)


def test_link_repo_attaches_once(db: Database) -> None:
    project = create_project(db, "meute")
    (repo,) = sync_repos(db, [_repo("/g/a", "a")])
    link_repo(db, project.id, repo.id)
    link_repo(db, project.id, repo.id)
    assert project_repo_ids(db, project.id) == [repo.id]


def test_the_project_takes_every_repository_of_that_name(db: Database) -> None:
    other, clone, main = sync_repos(
        db, [_repo("/g/main/poc", "poc"), _repo("/g/x/other", "other"), _repo("/w/poc", "POC")]
    )
    project = create_repo_project(db, "poc")
    assert project.name == "poc"
    assert project_repo_ids(db, project.id) == sorted([clone.id, main.id])
    assert other.id not in project_repo_ids(db, project.id)


def test_an_existing_project_of_that_name_is_reused_and_linked(db: Database) -> None:
    existing = create_project(db, "Poc")
    (repo,) = sync_repos(db, [_repo("/g/poc", "poc")])
    assert create_repo_project(db, " poc ") == existing
    assert create_repo_project(db, "POC") == existing
    assert list_projects(db) == [existing]
    assert project_repo_ids(db, existing.id) == [repo.id]


def test_an_empty_name_is_refused(db: Database) -> None:
    with pytest.raises(InvalidInput, match="empty"):
        create_repo_project(db, "  ")
