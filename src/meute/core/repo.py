"""Repositories discovered on disk and remembered in the database."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.errors import InvalidInput
from meute.core.instants import format_instant
from meute.core.json_types import JsonObject
from meute.core.paths import shown_path
from meute.core.project import RepoId, name_key
from meute.core.text import printable


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


def repo_matches(repos: Sequence[Repo], wanted: Path | str) -> list[Repo]:
    """Return the repositories at the path `wanted`, or named `wanted` (by `name_key`)."""
    if isinstance(wanted, Path):
        return [repo for repo in repos if repo.path == wanted]
    key = name_key(wanted)
    return [repo for repo in repos if name_key(repo.name) == key]


def find_repo(repos: Sequence[Repo], wanted: Path | str) -> Repo:
    """Return the one repository `wanted`: at that path (resolved by the caller), or of that name.

    Raises:
        InvalidInput: no repository matches, or several repositories bear that name.
    """
    matches = repo_matches(repos, wanted)
    if not matches:
        message = f"unknown repository: {printable(str(wanted))}"
        raise InvalidInput(message)
    if len(matches) > 1:
        paths = ", ".join(shown_path(repo.path, None) for repo in matches)
        message = f"ambiguous repository {printable(str(wanted).strip())}: {paths} (give its path)"
        raise InvalidInput(message)
    return matches[0]
