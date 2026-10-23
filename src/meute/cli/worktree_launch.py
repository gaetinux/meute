"""Launching a session in a new worktree: the checks, `git worktree add`, then the launch."""

from collections.abc import Callable, Mapping
from pathlib import Path

from meute.cli.context import ENVIRONMENT_ERRORS
from meute.cli.git_errors import find_git_or_fail, git_errors
from meute.core.errors import InvalidInput, MeuteError, PromptNotPasted
from meute.core.paths import shown_path
from meute.core.worktrees import branch_error, worktree_path
from meute.git.worktree import add_worktree, check_branch


def _taken(repo: Path, path: Path) -> Path | None:
    """The first link from `<repo>.worktrees` down to `path`, or `path` when it exists.

    A link on the way could lead the worktree out of `<repo>.worktrees`.
    """
    base = worktree_path(repo, "")  # `<repo>.worktrees` itself
    if base.is_symlink():
        return base
    folder = base
    for part in path.relative_to(base).parts:
        folder /= part
        if folder.is_symlink() or (folder == path and folder.exists()):
            return folder
    return None


def create_worktree(environ: Mapping[str, str], repo: Path, branch: str) -> Path:
    """Create `<repo>.worktrees/<branch>` on a new branch from HEAD; return its folder.

    The checks run in order, and the first that fails stops: the name (`branch_error`), the
    folder (it must not exist), `git check-ref-format --branch`, then `git worktree add`.

    Raises:
        InvalidInput: the name or the folder was refused; git never ran.
        MeuteError: git is missing, refused the name, failed or timed out.
    """
    error = branch_error(branch)
    if error is not None:
        raise InvalidInput(error)
    path = worktree_path(repo, branch)
    taken = _taken(repo, path)
    if taken is not None:
        message = f"folder already exists: {shown_path(taken, Path.home())}"
        raise InvalidInput(message)
    git = find_git_or_fail(environ)
    with git_errors():
        check_branch(git, repo, branch, environ=environ)
        add_worktree(git, repo, path, branch, environ=environ)
    return path


def launch_in_new_worktree[T](
    environ: Mapping[str, str], repo: Path, branch: str, launch: Callable[[Path], T]
) -> T:
    """Create the worktree of `branch` (see `create_worktree`), then `launch` in its folder.

    Raises:
        InvalidInput: the name or the folder was refused; nothing was created.
        MeuteError: the worktree could not be created, or the launch failed after it was;
            the worktree is then kept, and the message says where.
        PromptNotPasted: Claude was launched but not ready in time for the task text.
    """
    path = create_worktree(environ, repo, branch)
    try:
        return launch(path)
    except PromptNotPasted:
        raise
    except (MeuteError, *ENVIRONMENT_ERRORS) as failure:
        shown = shown_path(path, Path.home())
        message = f"worktree created at {shown} but the launch failed: {failure}"
        raise MeuteError(message) from failure
