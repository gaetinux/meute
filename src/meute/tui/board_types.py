"""What the board is given: where its data comes from, and what the configuration says."""

from dataclasses import dataclass
from datetime import UTC, tzinfo
from typing import Protocol

from meute.core.board_view import BoardAction, BoardData


class BoardBackend(Protocol):
    """Where the board reads its data and sends its actions; both raise `MeuteError`."""

    def load(self) -> BoardData | None:
        """Return the current data, or `None` when nothing changed since the last load."""
        ...

    def perform(self, action: BoardAction) -> None:
        """Carry out `action`."""
        ...


@dataclass(frozen=True, slots=True, kw_only=True)
class BoardOptions:
    """What the configuration says: details shown, local zone of the times, launch mode."""

    show_details: bool = True
    local: tzinfo = UTC
    permission_mode: str = "auto"


DEFAULT_OPTIONS = BoardOptions()
