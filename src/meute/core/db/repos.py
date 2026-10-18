"""Discovered repositories in the database."""

from collections.abc import Sequence
from pathlib import Path

from meute.core.db.connection import Database
from meute.core.db.rows import as_integer, as_text, fetch_all
from meute.core.instants import from_db, to_db
from meute.core.project import RepoId
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
