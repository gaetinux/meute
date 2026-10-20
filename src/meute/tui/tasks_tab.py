"""The Tasks tab: a placeholder until the task view lands."""

from textual.content import Content

from meute.core.board_header import tasks_totals
from meute.core.board_view import BoardData

_EMPTY = "No tasks yet."
_FOOTER = "Tab sessions · ? keys"
_KEYS_HELP = "Tab sessions · q detach\n? or Esc close this list"


class TasksTab:
    """The Tasks view; it has no keys of its own yet."""

    selected = -1

    def totals(self) -> str:
        """The open and overdue tasks."""
        return tasks_totals(0, 0)

    def rebuild(self, data: BoardData, width: int) -> None:
        """Nothing to rebuild yet."""

    def fit(self, width: int) -> bool:  # noqa: ARG002 — keeps the TabController signature
        """Nothing depends on the width yet."""
        return False

    def handle_key(self, key: str) -> bool:  # noqa: ARG002 — keeps the TabController signature
        """No key is the tab's."""
        return False

    def click(self, y: int, x: int) -> None:
        """Nothing to click yet."""

    def lines(self, *, focused: bool) -> Content:  # noqa: ARG002 — keeps the TabController signature
        """The placeholder."""
        return Content(_EMPTY)

    def quota(self) -> Content | None:
        """The quota bars belong to the Sessions tab."""
        return None

    def details(self, width: int) -> Content | None:  # noqa: ARG002 — keeps the TabController signature
        """No details yet."""
        return None

    def prompt(self) -> str | None:
        """No confirmation."""
        return None

    def footer(self) -> str:
        """The one-line keys."""
        return _FOOTER

    def keys_help(self) -> str:
        """The full list of keys."""
        return _KEYS_HELP
