"""The Sessions tab: its cursor, its keys and clicks, the stop confirmation."""

from collections.abc import Callable
from datetime import tzinfo
from typing import assert_never

from textual.content import Content

from meute.core.board_header import board_totals
from meute.core.board_sessions import line_at, line_entry, line_group, line_info
from meute.core.board_view import (
    FOOTER,
    KEYS_HELP,
    BoardAction,
    BoardData,
    BoardEntry,
    claude_action,
    confirm_stop_text,
    ended_notice,
    enter_action,
    new_action,
    stop_target,
)
from meute.core.session import Session, SessionId
from meute.core.sessions_view import (
    CardLine,
    HeaderLine,
    InfoLine,
    RefLine,
    RepoLine,
    SectionLine,
    SessionLine,
    section_key,
    session_index,
)
from meute.tui.sessions_cursor import SessionsCursor
from meute.tui.sessions_pane import details_content, quota_content, view_content

_ACTION_KEYS = frozenset({"enter", "c", "n", "x"})


class SessionsTab:
    """The Sessions view; the board gives it where to send actions, notices and stops."""

    def __init__(  # noqa: PLR0913 — the board's callbacks and options, all keyword-only
        self,
        *,
        perform: Callable[[BoardAction], None],
        notice: Callable[[str], None],
        stop: Callable[[Session], None],
        is_stopping: Callable[[SessionId], bool],
        local: tzinfo,
        show_details: bool,
    ) -> None:
        self._perform = perform
        self._notice = notice
        self._stop = stop
        self._is_stopping = is_stopping
        self._local = local
        self._show_details = show_details
        self.cursor = SessionsCursor()
        self._confirming: Session | None = None

    @property
    def width(self) -> int:
        """The width the cards are laid out for."""
        return self.cursor.width

    @property
    def selected(self) -> int:
        """The selected line of the view, -1 when nothing is selectable."""
        return self.cursor.selected

    def totals(self) -> str:
        """The live sessions with their summed duration and cost."""
        return board_totals(self.cursor.model.data)

    def rebuild(self, data: BoardData, width: int) -> None:
        """Take the new data, keeping the selection and the folds."""
        _ = width  # the cards follow the board's own width, given to `fit`
        self.cursor.rebuild(data)

    def fit(self, width: int) -> bool:
        """Lay the cards out for `width`; `True` when that changed them."""
        if width == self.cursor.width:
            return False
        self.cursor.resize(width)
        return True

    def handle_key(self, key: str) -> bool:
        """Apply `key`; `False` when the board should deal with it."""
        confirming, self._confirming = self._confirming, None
        if confirming is not None:  # a pending stop swallows any key
            if key == "y":
                self._stop(confirming)
            return True
        if self.cursor.handle_key(key):
            return True
        if key in _ACTION_KEYS:
            self._act(key)
            return True
        return False

    def _act(self, key: str) -> None:
        entry = line_entry(self.cursor.model, self.cursor.selected)
        if entry is None:
            group = line_group(self.cursor.model, self.cursor.selected)  # a folded group's header
            if key == "enter" and group is not None:
                self.cursor.fold(group, fold=False)
        elif key == "enter":
            self._show(entry)
        elif key == "c":
            self._perform(claude_action(entry))
        elif key == "n":
            self._perform(new_action(entry))
        elif key == "x":
            target = stop_target(entry)
            self._confirming = None if target is None or self._is_stopping(target.id) else target

    def click(self, y: int, x: int) -> None:
        """Select or fold the line at row `y`; like a key, a click only cancels a stop."""
        _ = x
        if self._confirming is not None:
            self._confirming = None
            return
        line = line_at(self.cursor.model, y)
        match line:
            case SessionLine():
                self.cursor.selected = y
                entry = line_entry(self.cursor.model, y)
                if entry is not None:
                    self._show(entry)
            case RepoLine():
                self.cursor.selected = y
            case CardLine() | RefLine():  # the card's first line, in "Needs you" for a reference
                index = session_index(self.cursor.model.view, line.session_id)
                self.cursor.selected = index if index >= 0 else self.cursor.selected
            case HeaderLine():
                self.cursor.fold(line.group, fold=not line.collapsed)
            case SectionLine():
                self.cursor.fold(section_key(line.section), fold=not line.collapsed)
            case InfoLine() | None:
                pass
            case _:
                assert_never(line)

    def _show(self, entry: BoardEntry) -> None:
        """Do what Enter does on `entry`, or say why an ended session cannot show."""
        notice = ended_notice(entry)
        if notice is None:
            self._perform(enter_action(entry))
        else:
            self._notice(notice)

    def lines(self, *, focused: bool) -> Content:
        """The grouped sessions, the selected card highlighted."""
        return view_content(
            self.cursor.model, self.cursor.selected, focused=focused, width=self.cursor.width
        )

    def quota(self, width: int) -> Content | None:  # noqa: ARG002 — the bars have their own width
        """The quota bars, when the usage is known."""
        quota = self.cursor.model.data.quota
        return None if quota is None else quota_content(quota, self._local)

    def details(self, width: int) -> Content | None:
        """The selected session's details, when shown and there is one."""
        if not self._show_details:
            return None
        info = line_info(self.cursor.model, self.cursor.selected)
        return None if info is None else details_content(self.cursor.model, info, width)

    def prompt(self) -> str | None:
        """The pending stop confirmation, which takes over the footer."""
        return None if self._confirming is None else confirm_stop_text(self._confirming.title)

    def footer(self) -> str:
        """The one-line keys."""
        return FOOTER

    def keys_help(self) -> str:
        """The full list of keys."""
        return KEYS_HELP
