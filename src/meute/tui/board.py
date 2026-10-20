"""The dashboard: a Textual app drawn from `meute.core.board_sessions`."""

from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, tzinfo
from functools import partial
from typing import ClassVar, Protocol, assert_never

from textual import events
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.content import Content
from textual.geometry import Region
from textual.widgets import Static

from meute.core.board_header import Tab, board_totals, tabs_line
from meute.core.board_sessions import line_at, line_entry, line_group, line_info
from meute.core.board_view import (
    BOARD_TITLE,
    FOOTER,
    KEYS_HELP,
    BoardAction,
    BoardData,
    BoardEntry,
    Detach,
    StopSession,
    claude_action,
    confirm_stop_text,
    ended_notice,
    enter_action,
    error_text,
    new_action,
    stop_target,
    stopping_text,
)
from meute.core.errors import MeuteError
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
from meute.tui.sessions_pane import (
    details_content,
    quota_content,
    tabs_content,
    view_content,
)


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
    """What the configuration says about the board: details shown, local zone of the times."""

    show_details: bool = True
    local: tzinfo = UTC


_DEFAULT_OPTIONS = BoardOptions()


class BoardApp(App[None]):
    """The Sessions view: quotas on top, grouped sessions, the selected one's details."""

    TITLE = BOARD_TITLE
    CSS: ClassVar[str] = """
    #quota { height: auto; }
    #sessions { height: 1fr; }
    #board { text-wrap: nowrap; text-overflow: ellipsis; }
    #details { height: auto; max-height: 50%; }
    #footer { dock: bottom; }
    """

    def __init__(
        self,
        backend: BoardBackend,
        options: BoardOptions = _DEFAULT_OPTIONS,
        *,
        poll_seconds: float = 0.5,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._poll_seconds = poll_seconds
        self._show_details = options.show_details
        self._local = options.local
        self._cursor = SessionsCursor()
        self._confirming: Session | None = None
        self._error: str | None = None
        self._notice: str | None = None  # shown in the footer until the next key or click
        self._stopping: dict[SessionId, str] = {}  # sessions being stopped: id -> title
        self._keys_help = False
        # Held, not queried: at quit the timer may still tick after the widgets left the DOM.
        self._title = Static(id="title")
        self._quota = Static(id="quota")
        self._board = Static(id="board")
        self._sessions = VerticalScroll(self._board, id="sessions")
        self._details = Static(id="details")
        self._footer = Static(id="footer")

    def compose(self) -> ComposeResult:
        yield self._title
        yield self._quota
        yield self._sessions
        yield self._details
        yield self._footer

    def on_mount(self) -> None:
        self._reload()
        _ = self.set_interval(self._poll_seconds, self._reload)
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        """The terminal changed size: the cards are laid out again for the new width."""
        self.call_after_refresh(self._fit)

    def _fit(self) -> None:
        """Lay the cards out for the width the board really has, then redraw."""
        width = self._board.size.width
        if width > 0 and width != self._cursor.width:
            self._cursor.resize(width)
            self._draw()

    # Every key comes here, not through bindings, so that a pending stop confirmation
    # swallows any key; ctrl+q stays Textual's own priority binding and quits.
    def on_key(self, event: events.Key) -> None:
        self._error = self._notice = None
        confirming, self._confirming = self._confirming, None
        if confirming is not None:
            if event.key == "y":
                self._stop(confirming)
        else:
            self._handle_key(event.key)
        self._draw()
        if self._cursor.selected >= 0:
            region = Region(0, self._cursor.selected, 1, 1)
            self.call_after_refresh(self._sessions.scroll_to_region, region, animate=False)

    def _handle_key(self, key: str) -> None:
        if self._cursor.handle_key(key):
            return
        if key == "question_mark":
            self._keys_help = not self._keys_help
        elif key == "escape":
            self._keys_help = False
        elif key == "q":
            self._perform(Detach())
        else:
            self._act(key)

    def _act(self, key: str) -> None:
        entry = line_entry(self._cursor.model, self._cursor.selected)
        if entry is None:
            group = line_group(self._cursor.model, self._cursor.selected)  # a folded group's header
            if key == "enter" and group is not None:
                self._cursor.fold(group, fold=False)
        elif key == "enter":
            self._show(entry)
        elif key == "c":
            self._perform(claude_action(entry))
        elif key == "n":
            self._perform(new_action(entry))
        elif key == "x":
            target = stop_target(entry)
            self._confirming = None if target is None or target.id in self._stopping else target

    def on_click(self, event: events.Click) -> None:
        if event.widget is not self._board:
            return
        self._error = self._notice = None
        if self._confirming is not None:  # like a key, a click only cancels the stop
            self._confirming = None
        else:
            self._click(round(event.y))
        self._draw()

    def _click(self, index: int) -> None:
        line = line_at(self._cursor.model, index)
        match line:
            case SessionLine():
                self._cursor.selected = index
                entry = line_entry(self._cursor.model, index)
                if entry is not None:
                    self._show(entry)
            case RepoLine():
                self._cursor.selected = index
            case CardLine() | RefLine():  # the card's first line, in "Needs you" for a reference
                index = session_index(self._cursor.model.view, line.session_id)
                self._cursor.selected = index if index >= 0 else self._cursor.selected
            case HeaderLine():
                self._cursor.fold(line.group, fold=not line.collapsed)
            case SectionLine():
                self._cursor.fold(section_key(line.section), fold=not line.collapsed)
            case InfoLine() | None:
                pass
            case _:
                assert_never(line)

    def _show(self, entry: BoardEntry) -> None:
        """Do what Enter does on `entry`, or say why an ended session cannot show."""
        self._notice = ended_notice(entry)
        if self._notice is None:
            self._perform(enter_action(entry))

    def _reload(self) -> None:
        error_before = self._error
        try:
            data = self._backend.load()
        except MeuteError as error:
            self._error = str(error)
            data = None
        else:
            if data is not None:
                self._cursor.rebuild(data)
        if data is not None or self._error != error_before:
            self._draw()

    def _perform(self, action: BoardAction) -> None:
        try:
            self._backend.perform(action)
        except MeuteError as error:
            self._error = str(error)

    def _stop(self, session: Session) -> None:
        """Stop `session` in a thread worker: tmux may take seconds to answer."""
        self._stopping[session.id] = session.title
        _ = self.run_worker(partial(self._stop_off_thread, session.id), thread=True)

    def _stop_off_thread(self, session_id: SessionId) -> None:
        """Run in the worker thread: only `call_from_thread` may touch the app from here."""
        error: str | None = None
        try:
            self._backend.perform(StopSession(session_id=session_id))
        except MeuteError as failure:
            error = str(failure)
        with suppress(RuntimeError):  # the app already quit: nobody left to tell
            self.call_from_thread(self._stopped, session_id, error)

    def _stopped(self, session_id: SessionId, error: str | None) -> None:
        """Report the end of a stop: its error if any, then a forced reread."""
        _ = self._stopping.pop(session_id, None)
        if error is not None:
            self._error = error
        self._reload()
        self._draw()

    def watch_app_focus(self) -> None:
        """Redraw when the terminal says the board gained or lost the focus."""
        self._draw()

    def _draw(self) -> None:
        focused = self.app_focus
        width = self.size.width or self._cursor.width
        tabs = tabs_line(
            Tab.SESSIONS, overdue=0, totals=board_totals(self._cursor.model.data), width=width
        )
        self._title.update(tabs_content(tabs, focused=focused))
        quota = self._cursor.model.data.quota
        self._quota.display = quota is not None
        if quota is not None:
            self._quota.update(quota_content(quota, self._local))
        board, selected = self._cursor.model, self._cursor.selected
        self._board.update(view_content(board, selected, focused=focused, width=self._cursor.width))
        info = line_info(self._cursor.model, self._cursor.selected) if self._show_details else None
        self._details.display = info is not None
        if info is not None:
            self._details.update(details_content(self._cursor.model, info, width))
        self._footer.update(Content(self._footer_text()))
        self.call_after_refresh(self._fit)  # a scrollbar that came or went changes the width

    def _footer_text(self) -> str:
        if self._error is not None:
            return error_text(self._error)
        if self._confirming is not None:
            return confirm_stop_text(self._confirming.title)
        if self._stopping:
            return stopping_text(next(reversed(self._stopping.values())))
        if self._notice is not None:
            return self._notice
        return KEYS_HELP if self._keys_help else FOOTER
