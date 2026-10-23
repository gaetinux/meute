"""The repository a launch in a folder belongs to, linked worktrees included."""

from pathlib import Path

from meute.cli.context import CliContext
from meute.cli.session_launch import resolve_folder
from meute.core.db.repos import list_repos
from meute.core.errors import InvalidInput
from meute.core.paths import shown_path
from meute.core.project import RepoId
from meute.core.repo import repo_holding
from meute.git.discover import main_repo_of


def repo_id_of_folder(ctx: CliContext, folder: Path) -> RepoId | None:
    """Return the id of the known repository holding `folder`, or its worktree's main one."""
    resolved = folder.resolve()
    repo = repo_holding(resolved, list_repos(ctx.db), main_repo_of(resolved))
    return None if repo is None else repo.id


def main_repo_or_fail(folder: Path) -> Path:
    """Return the main folder of the repository holding `folder`, linked worktrees included.

    Raises:
        InvalidInput: the folder does not exist, or is in no git repository.
    """
    path = resolve_folder(folder)
    repo = main_repo_of(path)
    if repo is None:
        message = f"not in a git repository: {shown_path(path, Path.home())}"
        raise InvalidInput(message)
    return repo
