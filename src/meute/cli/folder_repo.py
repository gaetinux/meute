"""The repository a launch in a folder belongs to, linked worktrees included."""

from pathlib import Path

from meute.cli.context import CliContext
from meute.core.db.repos import list_repos
from meute.core.project import RepoId
from meute.core.repo import repo_holding
from meute.git.discover import main_repo_of


def repo_id_of_folder(ctx: CliContext, folder: Path) -> RepoId | None:
    """Return the id of the known repository holding `folder`, or its worktree's main one."""
    resolved = folder.resolve()
    repo = repo_holding(resolved, list_repos(ctx.db), main_repo_of(resolved))
    return None if repo is None else repo.id
