"""Git worktree commands: the list, a branch name check, creation, checks and removal."""

from collections.abc import Mapping, Sequence
from pathlib import Path

from meute.git.run import read_git, write_git

CHECK_TIMEOUT = 5.0
ADD_TIMEOUT = 30.0
REMOVE_TIMEOUT = 30.0
_NO_SIGNATURES = ("-c", "log.showSignature=false")  # `gpg.program` would run otherwise


def list_worktrees_text(
    git: Path, repo: Path, *, timeout: float, environ: Mapping[str, str]
) -> str:
    """The output of `git worktree list --porcelain -z` in `repo`, read with the read guards.

    Raises:
        GitError: git is missing, failed or timed out.
    """
    return read_git(
        git, repo, ["worktree", "list", "--porcelain", "-z"], timeout=timeout, environ=environ
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


def worktree_changes(git: Path, folder: Path, *, environ: Mapping[str, str]) -> tuple[str, ...]:
    """The lines of `git status --porcelain` in `folder`, read with the read guards.

    Raises:
        GitError: git failed, is missing or timed out.
    """
    text = read_git(git, folder, ["status", "--porcelain"], timeout=CHECK_TIMEOUT, environ=environ)
    return tuple(line for line in text.splitlines() if line)


def worktree_only_commits(
    git: Path, folder: Path, branch: str | None, *, environ: Mapping[str, str]
) -> tuple[str, ...]:
    """The commits of HEAD in `folder` on no remote and no other local branch, newest first.

    `branch` is the worktree's own branch, left out of the other branches; None when detached.

    Raises:
        GitError: git failed, is missing or timed out.
    """
    # A pattern of `--exclude` before `--branches` leaves out the `refs/heads/` prefix.
    own = () if branch is None else (f"--exclude={branch}",)
    args = ["rev-list", "HEAD", "--not", "--remotes", *own, "--branches"]
    text = read_git(git, folder, args, timeout=CHECK_TIMEOUT, environ=environ)
    return tuple(line for line in text.splitlines() if line)


def oneline_log(
    git: Path, folder: Path, commits: Sequence[str], *, environ: Mapping[str, str]
) -> tuple[str, ...]:
    """The `git log --oneline` lines of exactly `commits`, in their order, signatures unchecked.

    Raises:
        GitError: git failed, is missing or timed out.
    """
    if not commits:
        return ()
    args = [*_NO_SIGNATURES, "log", "--oneline", "--no-walk=unsorted", *commits, "--"]
    text = read_git(git, folder, args, timeout=CHECK_TIMEOUT, environ=environ)
    return tuple(line for line in text.splitlines() if line)


def remove_worktree(
    git: Path, repo: Path, path: Path, *, force: bool, environ: Mapping[str, str]
) -> None:
    """Remove the worktree `path` of `repo`, its branch kept; `force` passes one `--force`.

    Raises:
        GitError: git refused (changes, a lock), failed, is missing or timed out.
    """
    flags = ["--force"] if force else []
    _ = write_git(
        git,
        repo,
        ["worktree", "remove", *flags, str(path)],
        timeout=REMOVE_TIMEOUT,
        environ=environ,
    )
