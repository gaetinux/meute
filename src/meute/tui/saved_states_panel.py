"""`S` and `O` on the Sessions tab: save the open sessions, list the saved states to reopen one."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import BoardAction, BoardData, SaveState
from meute.core.saved_state import NO_SAVED_STATE, SavedState, state_line
from meute.core.styled import Role, Span, StyledLine, clip, title_rule
from meute.tui.sessions_pane import highlighted_content

if TYPE_CHECKING:
    from datetime import datetime


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
        if key not in {"up", "down", "enter"}:
            self._open = False
        elif not self._states:
            return
        elif key == "enter":
            if not self._workers.is_reopening():
                self._workers.reopen(self._states[self._index()].name)
        else:
            moved = self._index() + (1 if key == "down" else -1)
            self._selected = self._states[min(max(moved, 0), len(self._states) - 1)].name

    def _index(self) -> int:
        """Where the chosen state is in the list: the first one when it is gone, or unset."""
        names = [state.name for state in self._states]
        return names.index(self._selected) if self._selected in names else 0

    def content(self, width: int) -> Content | None:
        """The list in colour, the chosen state highlighted; `None` while closed or unread."""
        now = self._now
        if not self._open or now is None:
            return None
        index = self._index()
        rule: StyledLine = title_rule(None, width, Role.DIM)
        rows = [(rule, False, False)]
        if not self._states:
            rows.append(((Span(NO_SAVED_STATE),), False, False))
        for n, state in enumerate(self._states):
            rows.append((clip((Span(state_line(state, now)),), width), n == index, False))
        return highlighted_content(rows, focused=True, width=width)
