"""The Git capabilities of the board, backed by the real git."""

from collections.abc import Callable, Collection, Mapping
from pathlib import Path

from meute.cli.git_errors import GIT_NOT_FOUND
from meute.cli.worktree_removal import inspect_worktree
from meute.core.errors import MeuteError
from meute.core.worktrees import Worktree, WorktreeCheck, parse_worktree_list
from meute.git.run import GitError, find_git
from meute.git.worktree import list_worktrees_text

LIST_TIMEOUT = 2.0


class CliBoardGit:
    """What the board asks git, read with the read guards."""

    def __init__(
        self, environ: Mapping[str, str], live_folders: Callable[[], Collection[Path]]
    ) -> None:
        """Read with `environ`; `live_folders` gives the folders where live sessions work."""
        self._environ = environ
        self._live_folders = live_folders
        self._git = find_git(environ)

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        """The linked worktrees of `repo`, or the text saying why they cannot be listed."""
        if self._git is None:
            return GIT_NOT_FOUND
        try:
            text = list_worktrees_text(self._git, repo, timeout=LIST_TIMEOUT, environ=self._environ)
        except GitError as failure:
            return str(failure)
        return parse_worktree_list(text, repo)

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        """Check `folder` before its worktree is removed, or say why it cannot be removed."""
        try:
            return inspect_worktree(self._environ, folder, self._live_folders())
        except MeuteError as refusal:
            return str(refusal)
