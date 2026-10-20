"""The contract between the board and its tabs."""

from typing import Protocol

from textual.content import Content

from meute.core.board_view import BoardData


class TabController(Protocol):
    """What the board asks of a tab; the board keeps loading, workers, footer and routing."""

    @property
    def selected(self) -> int:
        """The selected line, -1 when none."""
        ...

    def totals(self) -> str:
        """The totals shown at the right of the tabs line."""
        ...

    def rebuild(self, data: BoardData, width: int) -> None:
        """Take new data."""
        ...

    def fit(self, width: int) -> bool:
        """Lay out for `width`; `True` when that changed the lines."""
        ...

    def handle_key(self, key: str) -> bool:
        """Apply `key`; `False` when it is not the tab's."""
        ...

    def click(self, y: int, x: int) -> None:
        """Apply a click on line `y`, column `x`."""
        ...

    def lines(self, *, focused: bool) -> Content:
        """The tab's lines."""
        ...

    def quota(self) -> Content | None:
        """The quota bars, or `None` to hide them."""
        ...

    def details(self, width: int) -> Content | None:
        """The details of the selection, or `None` to hide them."""
        ...

    def prompt(self) -> str | None:
        """A pending confirmation for the footer."""
        ...

    def footer(self) -> str:
        """The one-line keys."""
        ...

    def keys_help(self) -> str:
        """The full list of keys."""
        ...
