"""The worktree of the launch form (`N`): its choices and the folder the form launches in."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

from meute.core.paths import resolved
from meute.core.worktrees import Worktree, branch_error, branch_from_title, worktree_path

if TYPE_CHECKING:
    from meute.core.launch_form import LaunchForm


@dataclass(frozen=True, slots=True, kw_only=True)
class NoWorktree:
    """Launch in the typed folder: `none`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class NewWorktree:
    """Create a worktree on the typed branch, then launch in it: `new`."""


@dataclass(frozen=True, slots=True, kw_only=True)
class ExistingWorktree:
    """Launch in an existing worktree.

    Attributes:
        index: Its index in `LaunchForm.worktrees`.
    """

    index: int


type WorktreeChoice = NoWorktree | NewWorktree | ExistingWorktree


def recommended(repo: Path | None, busy: frozenset[Path]) -> WorktreeChoice:
    """Return `new` when a live session already works in the folder of `repo`, else `none`."""
    return NewWorktree() if repo is not None and resolved(repo) in busy else NoWorktree()


def repo_path(form: "LaunchForm") -> Path | None:
    """Return the folder of the repository chosen in `form`, or None without one."""
    return None if form.repo is None else form.repos[form.repo].path


def chosen_worktree(form: "LaunchForm") -> WorktreeChoice:
    """Return the choice of `form`; without a repository, it is always `none`."""
    return NoWorktree() if form.repo is None else form.worktree


def with_worktrees(form: "LaunchForm", worktrees: tuple[Worktree, ...] | str) -> "LaunchForm":
    """Return `form` with the worktrees of its repository, or the error that listing them gave.

    The choice goes back to `none`, then to `new` when the folder of the repository is busy.
    """
    repo = repo_path(form)
    listed = () if isinstance(worktrees, str) else worktrees
    return replace(
        form,
        worktrees=listed,
        worktrees_error=worktrees if isinstance(worktrees, str) else None,
        worktree=recommended(repo, form.busy),
    )


def cycle_worktree(form: "LaunchForm", step: int) -> "LaunchForm":
    """Return `form` with its choice moved by `step` through `none`, `new`, then the existing."""
    if form.repo is None:
        return form
    choices: list[WorktreeChoice] = [
        NoWorktree(),
        NewWorktree(),
        *(ExistingWorktree(index=index) for index in range(len(form.worktrees))),
    ]
    position = (choices.index(form.worktree) + step) % len(choices)
    return replace(form, worktree=choices[position], error=None)


def retitled(form: "LaunchForm", title: str) -> "LaunchForm":
    """Return `form` with `title`, and the branch derived from it until it is typed."""
    branch = form.branch if form.branch_typed else branch_from_title(title)
    return replace(form, title=title, branch=branch, error=None)


def expanded(folder: str, home: Path) -> Path | str:
    """Return the typed folder as an absolute path, or the error saying why it is not one."""
    text = folder.strip()
    if not text:
        return "folder is empty"
    if text == "~":
        path = home
    elif text.startswith("~/"):
        path = home / text[2:]
    else:
        path = Path(text)
    if not path.is_absolute():
        return f"folder must be absolute: {folder.strip()}"
    return path


def target_folder(form: "LaunchForm", home: Path) -> Path | str:
    """Return the folder the form would launch in, or the error in its folder or branch."""
    repo = repo_path(form)
    if repo is None:  # without a repository the choice is always `none`
        return expanded(form.folder, home)
    match form.worktree:
        case NoWorktree():
            return expanded(form.folder, home)
        case NewWorktree():
            branch = form.branch.strip()
            error = branch_error(branch)
            return worktree_path(repo, branch) if error is None else error
        case ExistingWorktree(index=index):
            return form.worktrees[index].path
        case _:
            assert_never(form.worktree)
