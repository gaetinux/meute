"""The worktree model: the `git worktree list` output, branch names, paths and removal checks."""

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
_SHORT_HEAD = 7


@dataclass(frozen=True, slots=True, kw_only=True)
class Worktree:
    """A linked worktree of a repository.

    Attributes:
        path: Its absolute folder.
        branch: The checked-out branch without `refs/heads/`, or None when detached.
        head: The commit HEAD points to.
        locked: Whether `git worktree lock` protects it.
    """

    path: Path
    branch: str | None
    head: str
    locked: bool

    @property
    def label(self) -> str:
        """Its branch, or `(detached <commit>)` with the short commit when detached."""
        return self.branch or f"(detached {self.head[:_SHORT_HEAD]})"


@dataclass(frozen=True, slots=True, kw_only=True)
class WorktreeCheck:
    """What `W` needs to know before removing a worktree.

    Attributes:
        path: The worktree folder.
        repo: The main repository folder.
        branch: Its branch, or None when detached.
        changes: The lines of `git status --porcelain`.
        commits: The lines of `git log --oneline` of unpushed commits.
    """

    path: Path
    repo: Path
    branch: str | None
    changes: tuple[str, ...]
    commits: tuple[str, ...]

    @property
    def clean(self) -> bool:
        """Whether there is nothing to lose: no changes and no unpushed commits."""
        return not self.changes and not self.commits


def parse_worktree_list(text: str, main: Path) -> tuple[Worktree, ...]:
    """Read `git worktree list --porcelain -z`, keeping the linked worktrees.

    Fields end with a NUL, blocks with an empty field, so a path may hold a newline. Drops
    the first block (the main folder), any block whose path is `main`, the `prunable` and
    `bare` blocks, and any path that is not absolute. Never raises.
    """
    blocks: list[list[str]] = [[]]
    for field in text.split("\0"):
        if field:
            blocks[-1].append(field)
        elif blocks[-1]:
            blocks.append([])
    found: list[Worktree] = []
    for block in [b for b in blocks if b][1:]:
        worktree = _block(block)
        if worktree is not None and worktree.path != main:
            found.append(worktree)
    return tuple(found)


def _block(block: Sequence[str]) -> Worktree | None:
    path: Path | None = None
    branch: str | None = None
    head = ""
    locked = False
    for field in block:
        key, _, value = field.partition(" ")
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
    return Worktree(path=path, branch=branch, head=head, locked=locked)


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
