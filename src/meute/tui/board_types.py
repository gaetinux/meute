"""What the board is given: where its data comes from, and what the configuration says."""

from dataclasses import dataclass
from datetime import UTC, tzinfo
from pathlib import Path
from typing import Protocol

from meute.core.board_view import BoardAction, BoardData
from meute.core.worktrees import Worktree, WorktreeCheck


class BoardBackend(Protocol):
    """Where the board reads its data and sends its actions; both raise `MeuteError`."""

    def load(self) -> BoardData | None:
        """Return the current data, or `None` when nothing changed since the last load."""
        ...

    def perform(self, action: BoardAction) -> None:
        """Carry out `action`."""
        ...


class BoardGit(Protocol):
    """What the board asks git; both answer with the text of the error instead of raising."""

    def worktrees(self, repo: Path) -> tuple[Worktree, ...] | str:
        """The linked worktrees of `repo`, or why they cannot be listed."""
        ...

    def inspect(self, folder: Path) -> WorktreeCheck | str:
        """What removing the worktree `folder` would lose, or why it cannot be checked."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardOptions:
    """What the configuration says: details shown, local zone of the times, launch mode."""

    show_details: bool = True
    local: tzinfo = UTC
    permission_mode: str = "auto"


DEFAULT_OPTIONS = BoardOptions()
