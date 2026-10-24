"""`S` and `O` on the Sessions tab: save the open sessions, list the saved states to reopen one."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import BoardAction, BoardData, SaveState
from meute.core.saved_state import NO_SAVED_STATE, SavedState, state_line
from meute.core.styled import Role, Span, StyledLine, clip, title_rule
from meute.tui.sessions_pane import highlighted_content


class StateWorkers(Protocol):
    """Where `O` reopens a state, off the app's thread."""

    def reopen(self, name: str) -> None:
        """Reopen the saved state `name`; ignored while one is reopened."""
        ...

    def is_reopening(self) -> bool:
        """Whether a saved state is being reopened."""
        ...


class SavedStatesPanel(Static):
    """The list of the saved states, above the footer; hidden while it is closed."""

    DEFAULT_CSS = "SavedStatesPanel { height: auto; display: none; }"

    def __init__(self) -> None:
        super().__init__(id="saved-states")


class SavedStates:
    """`S` saves, `O` opens the list: ↑↓ choose, Enter reopens, any other key closes it."""

    def __init__(self, *, perform: Callable[[BoardAction], None], workers: StateWorkers) -> None:
        self._perform = perform
        self._workers = workers
        self._states: tuple[SavedState, ...] = ()
        self._now: datetime | None = None
        self._open = False
        self._selected: str | None = None  # the chosen state's name: a reread keeps it

    @property
    def is_open(self) -> bool:
        """Whether the list is open: it takes every key."""
        return self._open

    def refresh(self, data: BoardData) -> None:
        """Take a new reading of the board: its saved states and its clock."""
        self._states, self._now = data.saved_states, data.now

    def handle_key(self, key: str) -> bool:
        """`S` saves the open sessions, `O` opens the list on its first state; else `False`."""
        if key == "S":
            self._perform(SaveState())
        elif key == "O":
            self._open, self._selected = True, None
        else:
            return False
        return True

    def key(self, key: str) -> None:
        """Apply `key` to the open list."""
        index = self._index()
        if key in {"up", "down"}:
            if self._states:
                moved = min(max(index + (1 if key == "down" else -1), 0), len(self._states) - 1)
                self._selected = self._states[moved].name
        elif key == "enter":
            if self._states and not self._workers.is_reopening():
                self._workers.reopen(self._states[index].name)
        else:
            self._open = False

    def _index(self) -> int:
        """Where the chosen state is in the list: the first one when it is gone, or unset."""
        names = [state.name for state in self._states]
        return names.index(self._selected) if self._selected in names else 0

    def content(self, width: int) -> Content | None:
        """The list in colour, the chosen state highlighted; `None` while it is closed."""
        if not self._open:
            return None
        now = self._now or datetime.now(UTC)
        index = self._index()
        rule: StyledLine = title_rule(None, width, Role.DIM)
        rows = [(rule, False, False)]
        if not self._states:
            rows.append(((Span(NO_SAVED_STATE),), False, False))
        for n, state in enumerate(self._states):
            rows.append((clip((Span(state_line(state, now)),), width), n == index, False))
        return highlighted_content(rows, focused=True, width=width)
