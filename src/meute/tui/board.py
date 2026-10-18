"""The minimal dashboard: a Textual app drawn from `meute.core.board_view`."""

from typing import TYPE_CHECKING, ClassVar, Protocol

from textual import events
from textual.app import App, ComposeResult
from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import (
    BOARD_TITLE,
    FOOTER,
    BoardAction,
    BoardData,
    BoardEntry,
    StopSession,
    board_entries,
    board_layout,
    claude_action,
    confirm_stop_text,
    enter_action,
    entry_key,
    error_text,
    new_action,
    stop_target,
)
from meute.core.errors import MeuteError

if TYPE_CHECKING:
    from meute.core.session import Session

_EMPTY = BoardData(sessions=(), repos=(), orphans=(), home=None)
_SELECTED_STYLE = "reverse"


class BoardBackend(Protocol):
    """Where the board reads its data and sends its actions; both raise `MeuteError`."""

    def load(self) -> BoardData | None:
        """Return the current data, or `None` when nothing changed since the last load."""
        ...

    def perform(self, action: BoardAction) -> None:
        """Carry out `action`."""
        ...


class BoardApp(App[None]):
    """Lists the sessions and repositories; Enter, c, n and x act on the selected entry."""

    TITLE = BOARD_TITLE
    CSS: ClassVar[str] = "#footer { dock: bottom; }"

    def __init__(self, backend: BoardBackend, *, poll_seconds: float = 0.5) -> None:
        super().__init__()
        self._backend = backend
        self._poll_seconds = poll_seconds
        self._data = _EMPTY
        self._selected = 0
        self._confirming: Session | None = None
        self._error: str | None = None
        # Held, not queried: at quit the timer may still tick after the widgets left the DOM.
        self._board = Static(id="board")
        self._footer = Static(id="footer")

    def compose(self) -> ComposeResult:
        yield self._board
        yield self._footer

    def on_mount(self) -> None:
        self._reload()
        _ = self.set_interval(self._poll_seconds, self._reload)

    # Every key comes here, not through bindings, so that a pending stop confirmation
    # swallows any key; ctrl+q stays Textual's own priority binding and quits.
    def on_key(self, event: events.Key) -> None:
        self._error = None
        confirming, self._confirming = self._confirming, None
        if confirming is not None:
            if event.key == "y":
                self._perform(StopSession(session_id=confirming.id))
        else:
            self._handle_key(event.key)
        self._draw()

    def _handle_key(self, key: str) -> None:
        entries = board_entries(self._data)
        if key in {"up", "k"}:
            self._selected = max(self._selected - 1, 0)
        elif key in {"down", "j"}:
            self._selected = min(self._selected + 1, max(len(entries) - 1, 0))
        elif entries:
            entry = entries[self._selected]
            if key == "enter":
                self._perform(enter_action(entry))
            elif key == "c":
                self._perform(claude_action(entry))
            elif key == "n":
                self._perform(new_action(entry))
            elif key == "x":
                self._confirming = stop_target(entry)

    def _reload(self) -> None:
        error_before = self._error
        try:
            data = self._backend.load()
        except MeuteError as error:
            self._error = str(error)
            data = None
        else:
            if data is not None:
                self._replace(data)
        if data is not None or self._error != error_before:
            self._draw()

    def _replace(self, data: BoardData) -> None:
        """Swap the data in, keeping the selected entry when it is still there."""
        selected = self._selected_entry()
        keys = [entry_key(entry) for entry in board_entries(data)]
        if selected is not None and entry_key(selected) in keys:
            self._selected = keys.index(entry_key(selected))
        else:
            self._selected = min(self._selected, max(len(keys) - 1, 0))
        self._data = data

    def _selected_entry(self) -> BoardEntry | None:
        entries = board_entries(self._data)
        return entries[self._selected] if entries else None

    def _perform(self, action: BoardAction) -> None:
        try:
            self._backend.perform(action)
        except MeuteError as error:
            self._error = str(error)

    def _draw(self) -> None:
        # Content(...) never parses markup: titles, paths and names show literally.
        text_lines, indexes = board_layout(self._data)
        lines = [Content(line) for line in text_lines]
        if indexes:
            index = indexes[self._selected]
            lines[index] = lines[index].stylize(_SELECTED_STYLE)
        self._board.update(Content("\n").join(lines))
        self._footer.update(Content(self._footer_text()))

    def _footer_text(self) -> str:
        if self._error is not None:
            return error_text(self._error)
        if self._confirming is not None:
            return confirm_stop_text(self._confirming.title)
        return FOOTER
