"""Repository kind detection."""

from enum import Enum
from pathlib import Path


class RepoKind(Enum):
    """Kind of project found in a repository."""

    RUST = "rust"
    ANGULAR = "angular"
    NODE = "node"
    FASTAPI = "fastapi"
    PYTHON = "python"


def _mentions_fastapi(path: Path) -> bool:
    try:
        return "fastapi" in path.read_text(encoding="utf-8").lower()
    except (OSError, ValueError):
        return False


def detect_kind(folder: Path) -> RepoKind | None:
    """Detects the kind of project in `folder`; the first matching rule wins."""

    def has(name: str) -> bool:
        return (folder / name).is_file()

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
