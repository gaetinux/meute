"""Repository discovery under configured roots."""

import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from meute.git.kind import RepoKind, detect_kind

DEFAULT_DEPTH = 3
_SKIPPED = frozenset({"node_modules", "target", ".venv"})


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscoveredRepo:
    """A repository found on disk."""

    path: Path
    name: str
    kind: RepoKind | None
    worktrees: tuple[Path, ...]


@dataclass(slots=True)
class _Found:
    repos: set[Path]
    worktrees: dict[Path, set[Path]]


def discover(roots: Sequence[Path], max_depth: int = DEFAULT_DEPTH) -> list[DiscoveredRepo]:
    """Discovers repositories under `roots`, sorted by path, without duplicates.

    Missing or unreadable folders and non-UTF-8 names are ignored; symlinks are
    never followed.
    """
    found = _Found(repos=set(), worktrees={})
    for root in roots:
        try:
            resolved = root.resolve()
        except (OSError, RuntimeError):
            continue
        _walk(resolved, 0, max_depth, found)
    return [
        DiscoveredRepo(
            path=path,
            name=path.name,
            kind=detect_kind(path),
            worktrees=tuple(sorted(found.worktrees.get(path, ()))),
        )
        for path in sorted(found.repos)
    ]


def _walk(folder: Path, depth: int, max_depth: int, found: _Found) -> None:
    git = folder / ".git"
    try:
        mode = git.lstat().st_mode
    except OSError:
        mode = None
    if mode is not None:
        if stat.S_ISDIR(mode):
            found.repos.add(folder)
        elif stat.S_ISREG(mode) and (main := _main_repo_of_worktree(folder, git)) is not None:
            found.worktrees.setdefault(main, set()).add(folder)
        return
    if depth >= max_depth:
        return
    try:
        with os.scandir(folder) as entries:
            children = sorted(Path(entry.path) for entry in entries if _is_walkable(entry))
    except OSError:
        return
    for child in children:
        _walk(child, depth + 1, max_depth, found)


def _is_walkable(entry: os.DirEntry[str]) -> bool:
    name = entry.name
    if name.startswith(".") or name in _SKIPPED:
        return False
    try:
        name.encode("utf-8")
        return entry.is_dir(follow_symlinks=False)
    except (UnicodeEncodeError, OSError):
        return False


def _main_repo_of_worktree(folder: Path, git_file: Path) -> Path | None:
    """Returns the main repository when `git_file` points to `<main>/.git/worktrees/<name>`."""
    try:
        text = git_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    target = next(
        (
            line.removeprefix("gitdir:").strip()
            for line in text.splitlines()
            if line.startswith("gitdir:")
        ),
        None,
    )
    if not target:
        return None
    try:
        admin = (folder / target).resolve()
    except (OSError, RuntimeError):
        return None
    worktrees_dir = admin.parent
    git_dir = worktrees_dir.parent
    if worktrees_dir.name != "worktrees" or git_dir.name != ".git":
        return None
    return git_dir.parent


def expand_home(root: str, home: Path | None) -> Path:
    """Expands a leading `~` or `~/` using `home`; anything else is returned unchanged."""
    if home is None:
        return Path(root)
    if root == "~":
        return home
    if root.startswith("~/"):
        return home / root.removeprefix("~/")
    return Path(root)
