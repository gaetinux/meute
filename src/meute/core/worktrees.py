"""The worktree model: `git worktree list --porcelain`, branch names, paths and removal checks."""

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from meute.core.text import printable

_MAX_BRANCH = 60
_FORBIDDEN = frozenset("\\~^:?*[ ")
_UNSAFE = re.compile(r"[^a-z0-9_./-]")
_DASHES = re.compile(r"-{2,}")
_EDGES = "-./"


@dataclass(frozen=True, slots=True, kw_only=True)
class Worktree:
    """A linked worktree of a repository.

    Attributes:
        path: Its absolute folder.
        branch: The checked-out branch without `refs/heads/`, or None when detached.
        head: The commit HEAD points to.
        locked: Whether `git worktree lock` protects it.
        prunable: Whether git considers it stale.
    """

    path: Path
    branch: str | None
    head: str
    locked: bool
    prunable: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class WorktreeCheck:
    """What `W` needs to know before removing a worktree.

    Attributes:
        path: The worktree folder.
        repo: The main repository folder.
        branch: Its branch, or None when detached.
        locked: Whether the worktree is locked.
        changes: The lines of `git status --porcelain`.
        commits: The lines of `git log --oneline` of unpushed commits.
    """

    path: Path
    repo: Path
    branch: str | None
    locked: bool
    changes: tuple[str, ...]
    commits: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """Whether there is nothing to lose: no changes and no unpushed commits."""
        return not self.changes and not self.commits


def parse_worktree_list(text: str, main: Path) -> tuple[Worktree, ...]:
    """Read `git worktree list --porcelain`, keeping the linked worktrees.

    Drops the first block (the main folder), any block whose path is `main`, the `prunable`
    and `bare` blocks, and any path that is not absolute. Never raises.
    """
    blocks = [b for b in re.split(r"(?:\r?\n){2,}", text) if b.strip()]
    found: list[Worktree] = []
    for block in blocks[1:]:
        worktree = _block(block)
        if worktree is not None and worktree.path != main:
            found.append(worktree)
    return tuple(found)


def _block(block: str) -> Worktree | None:
    path: Path | None = None
    branch: str | None = None
    head = ""
    locked = False
    for line in block.splitlines():
        key, _, value = line.partition(" ")
        if key == "worktree":
            path = Path(value)
        elif key == "HEAD":
            head = value
        elif key == "branch":
            branch = value.removeprefix("refs/heads/")
        elif key == "locked":
            locked = True
        elif key in {"bare", "prunable"}:
            return None
    if path is None or not path.is_absolute():
        return None
    return Worktree(path=path, branch=branch, head=head, locked=locked, prunable=False)


def branch_from_title(title: str) -> str:
    """Derive a branch name from a session title: lowercase ASCII words joined by dashes."""
    name = _DASHES.sub("-", _UNSAFE.sub("-", title.lower())).strip(_EDGES)
    return name[:_MAX_BRANCH].strip(_EDGES)


def worktree_path(repo: Path, branch: str) -> Path:
    """Where a new worktree of `repo` for `branch` goes: `<repo>.worktrees/<branch>`."""
    return repo.parent / f"{repo.name}.worktrees" / branch


def branch_error(branch: str) -> str | None:
    """Check a branch name locally, before `git check-ref-format`; None when it is acceptable."""
    if not branch:
        return "branch is empty"
    if _invalid(branch):
        return f"invalid branch name: {branch}"
    return None


def _invalid(branch: str) -> bool:
    return (
        branch.startswith(("-", "/"))
        or branch.endswith(("/", ".", ".lock"))
        or ".." in branch
        or "//" in branch
        or "@{" in branch
        or any(c in _FORBIDDEN or unicodedata.category(c) == "Cc" for c in branch)
        or "." in branch.split("/")
    )


def listed_text(lines: Sequence[str], limit: int = 10) -> list[str]:
    """The first `limit` lines made printable, then `… and N more` when some were left."""
    shown = [printable(line) for line in lines[:limit]]
    if len(lines) > limit:
        shown.append(f"… and {len(lines) - limit} more")
    return shown
