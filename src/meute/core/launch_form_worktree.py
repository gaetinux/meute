"""The worktree of the launch form (`N`): its choices and the folder the form launches in."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, assert_never

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


def resolved(path: Path) -> Path:
    """Return `path` resolved; one that cannot be resolved stands for itself."""
    try:
        return path.resolve()
    except (ValueError, OSError, RuntimeError):
        return path


def recommended(repo: Path | None, busy: frozenset[Path]) -> WorktreeChoice:
    """Return `new` when a live session already works in the folder of `repo`, else `none`."""
    return NewWorktree() if repo is not None and resolved(repo) in busy else NoWorktree()


def chosen_worktree(form: "LaunchForm") -> WorktreeChoice:
    """Return the choice of `form`; without a repository, it is always `none`."""
    return NoWorktree() if form.repo is None else form.worktree


def with_worktrees(form: "LaunchForm", worktrees: tuple[Worktree, ...] | str) -> "LaunchForm":
    """Return `form` with the worktrees of its repository, or the error that listing them gave.

    The choice goes back to `none`, then to `new` when the folder of the repository is busy.
    """
    repo = None if form.repo is None else form.repos[form.repo].path
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
    match form.worktree:
        case NoWorktree():
            position = 0
        case NewWorktree():
            position = 1
        case ExistingWorktree(index=index):
            position = 2 + index
        case _:
            assert_never(form.worktree)
    position = (position + step) % (2 + len(form.worktrees))
    choice: WorktreeChoice
    if position == 0:
        choice = NoWorktree()
    elif position == 1:
        choice = NewWorktree()
    else:
        choice = ExistingWorktree(index=position - 2)
    return replace(form, worktree=choice, error=None)


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
    choice = chosen_worktree(form)
    match choice:
        case NoWorktree():
            return expanded(form.folder, home)
        case NewWorktree():
            branch = form.branch.strip()
            error = branch_error(branch)
            if error is not None:
                return error
            if form.repo is None:  # never: without a repository the choice is `none`
                return expanded(form.folder, home)
            return worktree_path(form.repos[form.repo].path, branch)
        case ExistingWorktree(index=index):
            return form.worktrees[index].path
        case _:
            assert_never(choice)
