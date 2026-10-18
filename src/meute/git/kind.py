"""Repository kind detection."""

import codecs
import os
import stat
from enum import Enum
from pathlib import Path

_TEXT_LIMIT = 1024 * 1024


class RepoKind(Enum):
    """Kind of project found in a repository."""

    RUST = "rust"
    ANGULAR = "angular"
    NODE = "node"
    FASTAPI = "fastapi"
    PYTHON = "python"


def _is_present(path: Path) -> bool:
    """Whether `path` is a regular file or a symlink, without following it."""
    try:
        mode = path.lstat().st_mode
    except OSError:
        return False
    return stat.S_ISREG(mode) or stat.S_ISLNK(mode)


def _read_regular(path: Path) -> bytes | None:
    """The first bytes of `path` if it is a regular file; a symlink, FIFO or device is not read."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            return handle.read(_TEXT_LIMIT)
    except OSError:
        return None


def _mentions_fastapi(path: Path) -> bool:
    data = _read_regular(path)
    if data is None:
        return False
    try:
        # Not final: a character cut by the read limit is dropped, invalid bytes still fail.
        text = codecs.getincrementaldecoder("utf-8")().decode(data, final=False)
    except ValueError:
        return False
    return "fastapi" in text.lower()


def detect_kind(folder: Path) -> RepoKind | None:
    """Detects the kind of project in `folder`; the first matching rule wins."""

    def has(name: str) -> bool:
        return _is_present(folder / name)

    if has("Cargo.toml"):
        return RepoKind.RUST
    if has("angular.json"):
        return RepoKind.ANGULAR
    if has("package.json"):
        return RepoKind.NODE
    if any(_mentions_fastapi(folder / name) for name in ("pyproject.toml", "requirements.txt")):
        return RepoKind.FASTAPI
    if any(has(name) for name in ("pyproject.toml", "requirements.txt", "setup.py")):
        return RepoKind.PYTHON
    return None
