"""Tests for discovered repositories stored in the database."""

from datetime import timedelta
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.repos import get_repo, list_repos, sync_repos
from meute.core.project import RepoId
from meute.core.repo import NewRepo, repo_to_json
from support import FIXED


def _new(path: str, kind: str | None = None) -> NewRepo:
    return NewRepo(path=Path(path), name=Path(path).name, kind=kind)


def test_sync_inserts_then_updates_without_deleting() -> None:
    now = [FIXED]
    with Database.in_memory(clock=lambda: now[0]) as db:
        sync_repos(db, [_new("/g/a", "node"), _new("/g/b")])
        now[0] = FIXED + timedelta(hours=1)
        repos = sync_repos(db, [_new("/g/a", "rust")])
    assert [(r.path, r.kind, r.discovered_at) for r in repos] == [
        (Path("/g/a"), "rust", FIXED),
        (Path("/g/b"), None, FIXED),
    ]


def test_sync_renames_known_paths(db: Database) -> None:
    sync_repos(db, [NewRepo(path=Path("/g/a"), name="a", kind=None)])
    (repo,) = sync_repos(db, [NewRepo(path=Path("/g/a"), name="renamed", kind=None)])
    assert repo.name == "renamed"


def test_list_is_sorted_by_name_case_insensitively(db: Database) -> None:
    sync_repos(db, [_new("/g/beta"), _new("/g/Alpha"), _new("/g/Écho"), _new("/g/alpha2")])
    assert [r.name for r in list_repos(db)] == ["Alpha", "alpha2", "beta", "Écho"]


def test_same_name_is_ordered_by_path(db: Database) -> None:
    sync_repos(db, [_new("/z/app"), _new("/a/app")])
    assert [r.path for r in list_repos(db)] == [Path("/a/app"), Path("/z/app")]


def test_repo_to_json(db: Database) -> None:
    (repo,) = sync_repos(db, [_new("/g/a", "node")])
    assert repo_to_json(repo) == {
        "id": repo.id,
        "path": "/g/a",
        "name": "a",
        "kind": "node",
        "discovered_at": "2026-10-14T08:30:00Z",
    }


def test_sql_metacharacters_in_names_are_data(db: Database) -> None:
    name = "x'); DROP TABLE repos; --"
    (repo,) = sync_repos(db, [NewRepo(path=Path("/g") / name, name=name, kind=None)])
    assert repo.name == name
    assert len(list_repos(db)) == 1


def test_get_repo_reads_one_repository_by_id(db: Database) -> None:
    stored = sync_repos(db, [NewRepo(path=Path("/g/a"), name="a", kind="rust")])
    assert get_repo(db, stored[0].id) == stored[0]
    assert get_repo(db, RepoId(stored[0].id + 1)) is None
