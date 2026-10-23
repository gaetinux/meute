"""The Git capabilities of the board, backed by the real git."""

from collections.abc import Mapping
from pathlib import Path

from meute.core.worktrees import Worktree, WorktreeCheck, parse_worktree_list
from meute.git.run import GitError, find_git
from meute.git.worktree import list_worktrees_text

LIST_TIMEOUT = 2.0


class CliBoardGit:
    """What the board asks git, read with the read guards."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self._environ = environ

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        """The linked worktrees of `repo`, or the text saying why they cannot be listed."""
        git = find_git(self._environ)
        if git is None:
            return "git not found"
        try:
            text = list_worktrees_text(git, repo, timeout=LIST_TIMEOUT, environ=self._environ)
        except GitError as failure:
            return str(failure)
        return parse_worktree_list(text, repo)

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        """Check `folder` before its worktree is removed (written in the next task)."""
        raise NotImplementedError(str(folder))
