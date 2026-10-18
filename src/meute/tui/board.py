"""The dashboard: a Textual app drawn from `meute.core.board_sessions`."""

from dataclasses import dataclass, replace
from datetime import UTC, tzinfo
from typing import TYPE_CHECKING, ClassVar, Protocol, assert_never

from textual import events
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.content import Content
from textual.geometry import Region
from textual.widgets import Static

from meute.core.board_sessions import (
    board_sessions,
    line_at,
    line_entry,
    line_group,
    line_info,
)
from meute.core.board_view import (
    BOARD_TITLE,
    FOOTER,
    BoardAction,
    BoardData,
    Detach,
    ShowSession,
    StopSession,
    claude_action,
    confirm_stop_text,
    enter_action,
    error_text,
    new_action,
    stop_target,
)
from meute.core.errors import MeuteError
from meute.core.sessions_view import (
    HeaderLine,
    InfoLine,
    RepoLine,
    SessionLine,
    ViewState,
    keep_selection,
    line_key,
    selectable,
)
from meute.tui.sessions_pane import details_content, quota_content, view_content

if TYPE_CHECKING:
    from meute.core.session import Session

_EMPTY = BoardData(sessions=(), repos=(), orphans=(), home=None)


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
    #details { height: auto; max-height: 50%; border-top: solid $secondary; }
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
        self._state = ViewState()
        self._model = board_sessions(_EMPTY, self._state)
        self._selected = -1  # a line index of the view; -1: nothing selectable
        self._confirming: Session | None = None
        self._error: str | None = None
        # Held, not queried: at quit the timer may still tick after the widgets left the DOM.
        self._quota = Static(id="quota")
        self._board = Static(id="board")
        self._sessions = VerticalScroll(self._board, id="sessions")
        self._details = Static(id="details")
        self._footer = Static(id="footer")

    def compose(self) -> ComposeResult:
        yield self._quota
        yield self._sessions
        yield self._details
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
        if self._selected >= 0:
            region = Region(0, self._selected, 1, 1)
            self.call_after_refresh(self._sessions.scroll_to_region, region, animate=False)

    def _handle_key(self, key: str) -> None:
        if key in {"up", "k"}:
            self._move(-1)
        elif key in {"down", "j"}:
            self._move(1)
        elif key == "a":
            self._set_state(replace(self._state, attention_only=not self._state.attention_only))
        elif key == "e":
            self._set_state(replace(self._state, show_ended=not self._state.show_ended))
        elif key in {"space", "left", "right"}:
            group = line_group(self._model, self._selected)
            if group is not None:
                folded = group in self._state.collapsed
                self._fold(group, fold=not folded if key == "space" else key == "left")
        elif key == "q":
            self._perform(Detach())
        else:
            self._act(key)

    def _act(self, key: str) -> None:
        entry = line_entry(self._model, self._selected)
        if entry is None:
            group = line_group(self._model, self._selected)  # a folded group's header
            if key == "enter" and group is not None:
                self._fold(group, fold=False)
        elif key == "enter":
            self._perform(enter_action(entry))
        elif key == "c":
            self._perform(claude_action(entry))
        elif key == "n":
            self._perform(new_action(entry))
        elif key == "x":
            self._confirming = stop_target(entry)

    def on_click(self, event: events.Click) -> None:
        if event.widget is not self._board:
            return
        self._error = None
        if self._confirming is not None:  # like a key, a click only cancels the stop
            self._confirming = None
        else:
            self._click(round(event.y))
        self._draw()

    def _click(self, index: int) -> None:
        line = line_at(self._model, index)
        match line:
            case SessionLine():
                self._selected = index
                self._perform(ShowSession(session_id=line.session_id))
            case RepoLine():
                self._selected = index
            case HeaderLine():
                self._fold(line.group, fold=not line.collapsed)
            case InfoLine() | None:
                pass
            case _:
                assert_never(line)

    def _move(self, delta: int) -> None:
        choices = selectable(self._model.view)
        if choices:
            position = choices.index(self._selected) if self._selected in choices else 0
            self._selected = choices[min(max(position + delta, 0), len(choices) - 1)]

    def _fold(self, group: str, *, fold: bool) -> None:
        """Fold or unfold `group`; the selection moves to its header, or into it from there."""
        if fold == (group in self._state.collapsed):
            return
        collapsed = self._state.collapsed
        header_selected = self._selected_key() == f"group:{group}"
        inside = line_group(self._model, self._selected) == group
        self._set_state(
            replace(self._state, collapsed=collapsed | {group} if fold else collapsed - {group}),
            old_group=group if fold and inside else None,
        )
        if not fold and header_selected:
            choices = selectable(self._model.view)
            members = (i for i in choices if line_group(self._model, i) == group)
            self._selected = next(members, self._selected)

    def _selected_key(self) -> str | None:
        line = line_at(self._model, self._selected)
        return None if line is None else line_key(line)

    def _set_state(self, state: ViewState, *, old_group: str | None = None) -> None:
        self._state = state
        self._rebuild(self._model.data, old_group=old_group)

    def _rebuild(self, data: BoardData, *, old_group: str | None = None) -> None:
        """Rebuild the view, keeping the selected line when it is still there."""
        choices = selectable(self._model.view)
        position = choices.index(self._selected) if self._selected in choices else 0
        old_key = self._selected_key()
        self._model = board_sessions(data, self._state)
        self._selected = keep_selection(old_key, self._model.view, position, old_group=old_group)

    def _reload(self) -> None:
        error_before = self._error
        try:
            data = self._backend.load()
        except MeuteError as error:
            self._error = str(error)
            data = None
        else:
            if data is not None:
                self._rebuild(data)
        if data is not None or self._error != error_before:
            self._draw()

    def _perform(self, action: BoardAction) -> None:
        try:
            self._backend.perform(action)
        except MeuteError as error:
            self._error = str(error)

    def _draw(self) -> None:
        quota = self._model.data.quota
        self._quota.display = quota is not None
        if quota is not None:
            self._quota.update(quota_content(quota, self._local))
        self._board.update(view_content(self._model, self._selected))
        info = line_info(self._model, self._selected) if self._show_details else None
        self._details.display = info is not None
        if info is not None:
            self._details.update(details_content(self._model, info))
        self._footer.update(Content(self._footer_text()))

    def _footer_text(self) -> str:
        if self._error is not None:
            return error_text(self._error)
        if self._confirming is not None:
            return confirm_stop_text(self._confirming.title)
        return FOOTER
