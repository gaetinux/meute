"""Repositories discovered on disk and remembered in the database."""

from collections.abc import Sequence
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


def _longest_holder(folder: Path, repos: Sequence[Repo]) -> Repo | None:
    holders = [repo for repo in repos if folder.is_relative_to(repo.path)]
    return max(holders, key=lambda held: len(held.path.parts), default=None)


def repo_holding(folder: Path, repos: Sequence[Repo], main_repo: Path | None) -> Repo | None:
    """Return the known repository `folder` belongs to, or `None`.

    That is the known repository with the longest path holding `folder`; failing that,
    the one holding `main_repo`, the main repository of a linked worktree.
    """
    found = _longest_holder(folder, repos)
    if found is None and main_repo is not None:
        return _longest_holder(main_repo, repos)
    return found
