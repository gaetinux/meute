"""Checking a linked worktree before its removal, then removing it with its branch kept.

The main folder of a repository, a locked worktree and a worktree where a live session works
are always refused, before git is asked to remove anything.
"""

from collections.abc import Collection, Iterable, Mapping
from pathlib import Path

from meute.cli.git_errors import find_git_or_fail, git_errors
from meute.core.board_actions import RemoveWorktree
from meute.core.errors import InvalidInput
from meute.core.git_folder import git_folder
from meute.core.paths import resolved, shown_path
from meute.core.session import Session, SessionId
from meute.core.session_state import is_live
from meute.core.statusline import StatuslineData
from meute.core.worktrees import WorktreeCheck, parse_worktree_list
from meute.git.discover import main_repo_of
from meute.git.worktree import (
    CHECK_TIMEOUT,
    list_worktrees_text,
    oneline_log,
    remove_worktree,
    worktree_changes,
    worktree_only_commits,
)

# The commits `listed_text` shows get their log line; the others stay bare, for the count.
SHOWN_COMMITS = 10
LIVE_SESSION = "a live session works in this worktree"
LOCKED = "the worktree is locked"


def live_session_folders(
    sessions: Iterable[Session], metrics: Mapping[SessionId, StatuslineData]
) -> tuple[Path, ...]:
    """The folders the live sessions work in: their own and the worktree Claude reported."""
    return tuple(
        folder
        for session in sessions
        if is_live(session.state)
        for folder in (session.cwd, git_folder(session, metrics.get(session.id)))
    )


def _not_linked(path: Path) -> InvalidInput:
    return InvalidInput(f"not a linked worktree: {shown_path(path, Path.home())}")


def inspect_worktree(
    environ: Mapping[str, str], folder: Path, live_folders: Collection[Path]
) -> WorktreeCheck:
    """Check that `folder` is a linked worktree that can go, then read what it would lose.

    The refusals come in order: the folder is missing; it is not a linked worktree of its
    repository (the main folder never is); it is locked; a folder of `live_folders` is in it.
    Then `git status --porcelain` and the commits on no remote and no other branch are read
    with the read guards.

    Raises:
        InvalidInput: one of the refusals above.
        MeuteError: git is missing, failed or timed out.
    """
    path = folder.resolve()
    if not path.is_dir():
        message = f"folder not found: {shown_path(path, Path.home())}"
        raise InvalidInput(message)
    repo = main_repo_of(path)
    if repo is None or repo == path:
        raise _not_linked(path)
    git = find_git_or_fail(environ)
    with git_errors():
        text = list_worktrees_text(git, repo, timeout=CHECK_TIMEOUT, environ=environ)
    listed = parse_worktree_list(text, repo)
    worktree = next((w for w in listed if resolved(w.path) == path), None)
    if worktree is None:
        raise _not_linked(path)
    if worktree.locked:
        raise InvalidInput(LOCKED)
    if any(live == path or path in live.parents for live in map(resolved, live_folders)):
        raise InvalidInput(LIVE_SESSION)
    with git_errors():
        changes = worktree_changes(git, path, environ=environ)
        commits = worktree_only_commits(git, path, worktree.branch, environ=environ)
        lines = oneline_log(git, path, commits[:SHOWN_COMMITS], environ=environ)
    return WorktreeCheck(
        path=path,
        repo=repo,
        branch=worktree.branch,
        changes=changes,
        commits=(*lines, *commits[SHOWN_COMMITS:]),
    )


def remove_checked(environ: Mapping[str, str], check: WorktreeCheck, *, force: bool) -> None:
    """Remove the worktree of `check`, its branch kept; without `force`, only when clean.

    Raises:
        InvalidInput: it is not clean and `force` is false; git never ran.
        MeuteError: git is missing, refused, failed or timed out.
    """
    if not force and not check.clean:
        shown = shown_path(check.path, Path.home())
        message = f"{shown} has uncommitted changes or unpushed commits"
        raise InvalidInput(message)
    git = find_git_or_fail(environ)
    with git_errors():
        remove_worktree(git, check.repo, check.path, force=force, environ=environ)


def perform_removal(
    environ: Mapping[str, str], action: RemoveWorktree, live_folders: Collection[Path]
) -> None:
    """Check the worktree of `action` again, then remove it (see `remove_checked`).

    Raises:
        InvalidInput: a refusal of `inspect_worktree` or `remove_checked`, or the worktree
            is not one of `action.repo`.
        MeuteError: git is missing, refused, failed or timed out.
    """
    check = inspect_worktree(environ, action.path, live_folders)
    if resolved(action.repo) != check.repo:
        raise _not_linked(check.path)
    remove_checked(environ, check, force=action.force)
