"""Git worktree commands: the list, a branch name check and the creation of a worktree."""

from collections.abc import Mapping
from pathlib import Path

from meute.git.run import read_git, write_git

CHECK_TIMEOUT = 5.0
ADD_TIMEOUT = 30.0


def list_worktrees_text(
    git: Path, repo: Path, *, timeout: float, environ: Mapping[str, str]
) -> str:
    """The output of `git worktree list --porcelain` in `repo`, read with the read guards.

    Raises:
        GitError: git is missing, failed or timed out.
    """
    return read_git(
        git, repo, ["worktree", "list", "--porcelain"], timeout=timeout, environ=environ
    )


def check_branch(git: Path, repo: Path, branch: str, *, environ: Mapping[str, str]) -> None:
    """Check `branch` with `git check-ref-format --branch`, read with the read guards.

    Raises:
        GitError: git refused the name, is missing or timed out.
    """
    _ = read_git(
        git, repo, ["check-ref-format", "--branch", branch], timeout=CHECK_TIMEOUT, environ=environ
    )


def add_worktree(
    git: Path, repo: Path, path: Path, branch: str, *, environ: Mapping[str, str]
) -> None:
    """Create the worktree `path` of `repo` on a new `branch` from HEAD, hooks kept.

    Raises:
        GitError: git failed, is missing or timed out.
    """
    _ = write_git(
        git,
        repo,
        ["worktree", "add", "--quiet", str(path), "-b", branch],
        timeout=ADD_TIMEOUT,
        environ=environ,
    )
