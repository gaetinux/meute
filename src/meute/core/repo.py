"""Repositories discovered on disk and remembered in the database."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.instants import format_instant
from meute.core.json_types import JsonObject
from meute.core.project import RepoId


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    """A repository stored in the database."""

    id: RepoId
    path: Path
    name: str
    kind: str | None
    discovered_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class NewRepo:
    """A repository found on disk, to be stored or refreshed."""

    path: Path
    name: str
    kind: str | None


def repo_to_json(repo: Repo) -> JsonObject:
    """Return the JSON form of `repo`."""
    return {
        "id": repo.id,
        "path": str(repo.path),
        "name": repo.name,
        "kind": repo.kind,
        "discovered_at": format_instant(repo.discovered_at),
    }
