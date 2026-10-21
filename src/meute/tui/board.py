"""The dashboard: a Textual app drawn from `meute.core.board_sessions`."""

from dataclasses import dataclass
from datetime import UTC, tzinfo
from typing import ClassVar, Protocol

from textual import events
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.content import Content
from textual.geometry import Region
from textual.widgets import Input, OptionList, Static

from meute.core.board_header import Tab, tab_at, tabs_line
from meute.core.board_view import (
    BOARD_TITLE,
    EDIT_FOOTER,
    BoardAction,
    BoardData,
    Detach,
    TaskAction,
    error_text,
)
from meute.core.errors import MeuteError
from meute.tui.board_workers import BoardWorkers
from meute.tui.sessions_pane import tabs_content
from meute.tui.sessions_tab import SessionsTab
from meute.tui.tab_controller import TabController
from meute.tui.tasks_tab import TasksTab


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
    AUTO_FOCUS = None  # the keys come to `on_key`; only an open task input takes the focus
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
        self._background = BoardWorkers(self, backend.perform, self._finished)
        self._sessions_tab = SessionsTab(
            perform=self._perform,
            notice=self._say,
            stop=self._background.stop,
            is_stopping=self._background.is_stopping,
            resume=self._background.resume,
            is_resuming=self._background.is_resuming,
            local=options.local,
            show_details=options.show_details,
        )
        self._tasks_tab = TasksTab(
            perform=self._perform,
            write=self._write,
            launch=self._background.launch,
            notice=self._say,
            fail=self._fail,
            local=options.local,
        )
        self._editor = self._tasks_tab.editor
        self._tabs: dict[Tab, TabController] = {
            Tab.SESSIONS: self._sessions_tab,
            Tab.TASKS: self._tasks_tab,
        }
        self._tab = Tab.SESSIONS
        self._error: str | None = None
        self._notice: str | None = None  # shown in the footer until the next key or click
        self._keys_help = False
        self._fitted_width = 0  # the board width the tabs were last fitted to
        # Held, not queried: at quit the timer may still tick after the widgets left the DOM.
        self._title = Static(id="title")
        self._quota = Static(id="quota")
        self._board = Static(id="board")
        self._sessions = VerticalScroll(self._board, id="sessions", can_focus=False)  # keys: on_key
        self._details = Static(id="details")
        self._footer = Static(id="footer")

    @property
    def _current(self) -> TabController:
        return self._tabs[self._tab]

    def compose(self) -> ComposeResult:
        yield self._title
        yield self._quota
        yield self._sessions
        yield self._details
        yield self._editor.widget
        yield self._footer

    def on_mount(self) -> None:
        if self.size.width > 0:  # the terminal's width until the board's own is known
            for tab in self._tabs.values():
                _ = tab.fit(self.size.width)
        self._reload()
        _ = self.set_interval(self._poll_seconds, self._reload)
        self.call_after_refresh(self._fit)

    def on_resize(self) -> None:
        """The terminal changed size: the cards are laid out again for the new width."""
        self.call_after_refresh(self._fit)

    def _fit(self) -> None:
        """Lay the tabs out for the width the board really has, then redraw."""
        width = self._board.size.width
        if width > 0 and width != self._fitted_width:
            self._fitted_width = width
            fitted = [tab.fit(width) for tab in self._tabs.values()]  # every tab, not the first
            if any(fitted):
                self._draw()

    # Every key comes here, not through bindings, so a pending stop swallows any key; ctrl+q
    # stays Textual's priority binding. An open task input takes every key but Escape.
    def on_key(self, event: events.Key) -> None:
        if self._editor.editing:
            if event.key in {"tab", "shift+tab"}:
                event.prevent_default()  # the focus stays in the input
            elif event.key == "escape":
                self._error = self._notice = None
                self._editor.cancel()
                self._draw()
            return
        self._error = self._notice = None
        if not self._current.handle_key(event.key):
            self._handle_key(event.key)
        self._draw()
        if self._current.selected >= 0:
            region = Region(0, self._current.selected, 1, 1)
            self.call_after_refresh(self._sessions.scroll_to_region, region, animate=False)

    def _handle_key(self, key: str) -> None:
        if key == "tab":
            self._tab = Tab.TASKS if self._tab is Tab.SESSIONS else Tab.SESSIONS
        elif key == "question_mark":
            self._keys_help = not self._keys_help
        elif key == "escape":
            self._keys_help = False
        elif key == "q":
            self._perform(Detach())

    def on_input_changed(self, event: Input.Changed) -> None:
        self._editor.preview(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._error = self._notice = None
        self._editor.submit_text(event.value)
        self._draw()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._error = self._notice = None
        self._editor.submit_choice(event.option_index)
        self._draw()

    def on_click(self, event: events.Click) -> None:
        if event.widget not in {self._board, self._title} or self._editor.editing:
            return
        self._error = self._notice = None
        if event.widget is self._title and self._current.prompt() is None:
            self._choose_tab(round(event.x))
        else:  # a pending prompt turns any click into its cancellation
            self._current.click(round(event.y), round(event.x))
        self._draw()

    def _choose_tab(self, x: int) -> None:
        """Choose the tab whose name was clicked."""
        width = self.size.width or self._sessions_tab.width
        line = tabs_line(
            self._tab,
            overdue=self._tasks_tab.overdue_count,
            totals=self._current.totals(),
            width=width,
        )
        self._tab = tab_at(line, x) or self._tab

    def _say(self, notice: str) -> None:
        self._notice = notice

    def _reload(self) -> None:
        error_before = self._error
        try:
            data = self._backend.load()
        except MeuteError as error:
            self._error = str(error)
            data = None
        else:
            if data is not None:
                for tab in self._tabs.values():
                    tab.rebuild(data, self._board.size.width)
        if data is not None or self._error != error_before:
            self._draw()

    def _perform(self, action: BoardAction) -> None:
        try:
            self._backend.perform(action)
        except MeuteError as error:
            self._error = str(error)

    def _write(self, action: TaskAction) -> None:
        """Send a task change, then reread whatever happened; raises `MeuteError`."""
        try:
            self._backend.perform(action)
        finally:
            self._reload()

    def _fail(self, message: str) -> None:
        self._error = message

    def _finished(self, error: str | None, notice: str | None) -> None:
        """Report the end of a worker's action: its error or notice, then a forced reread."""
        if error is not None:
            self._error = error
        if notice is not None:
            self._notice = notice
        self._reload()
        self._draw()

    def watch_app_focus(self) -> None:
        """Redraw when the terminal says the board gained or lost the focus."""
        self._draw()

    def _draw(self) -> None:
        focused = self.app_focus
        tab = self._current
        width = self.size.width or self._sessions_tab.width
        tabs = tabs_line(
            self._tab, overdue=self._tasks_tab.overdue_count, totals=tab.totals(), width=width
        )
        self._title.update(tabs_content(tabs, focused=focused))
        quota = tab.quota(width)
        self._quota.display = quota is not None
        if quota is not None:
            self._quota.update(quota)
        self._board.update(tab.lines(focused=focused))
        details = tab.details(width)
        self._details.display = details is not None
        if details is not None:
            self._details.update(details)
        self._footer.update(Content(self._footer_text()))
        self.call_after_refresh(self._fit)  # a scrollbar that came or went changes the width

    def _footer_text(self) -> str:
        prompt = self._current.prompt()
        if self._error is not None:
            return error_text(self._error)
        if prompt is not None:
            return prompt
        if (running := self._background.footer()) is not None:
            return running
        if self._notice is not None:
            return self._notice
        if self._editor.editing:
            return EDIT_FOOTER
        return self._current.keys_help() if self._keys_help else self._current.footer()
