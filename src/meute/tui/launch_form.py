"""The launch form (`N`) of the board: the panel that shows it and the state behind it."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from textual.content import Content
from textual.widgets import Static

from meute.core.board_view import BoardData, BoardEntry, LaunchBash, LaunchClaude
from meute.core.errors import MeuteError
from meute.core.launch_form import (
    LaunchForm,
    choose,
    erase,
    form_action,
    move,
    open_form,
    type_text,
    with_busy,
)
from meute.core.launch_form_view import form_lines
from meute.core.styled import StyledLine
from meute.tui.sessions_pane import styled_content

Launch = Callable[[LaunchBash | LaunchClaude], None]


class LaunchFormPanel(Static):
    """The form's lines, above the footer; hidden while the form is closed."""

    DEFAULT_CSS = "LaunchFormPanel { height: auto; display: none; }"

    def __init__(self) -> None:
        super().__init__(id="launch-form")


class FormSession:
    """The form while it is open: it takes every key, and a launch that fails keeps it."""

    def __init__(self, *, launch: Launch, default_mode: str) -> None:
        self._launch = launch
        self._default_mode = default_mode
        self._form: LaunchForm | None = None

    @property
    def is_open(self) -> bool:
        """Whether the form is open."""
        return self._form is not None

    def open(self, data: BoardData, entry: BoardEntry | None) -> None:
        """Open the form on the selected `entry`."""
        self._form = open_form(data, entry, default_mode=self._default_mode, now=_now(data))

    def refresh(self, data: BoardData) -> None:
        """Take a new reading of the board: only the busy folders change."""
        if self._form is not None:
            self._form = with_busy(self._form, data)

    def key(self, key: str, character: str | None, data: BoardData) -> None:
        """Apply `key` to the open form; `character` is what the key types, if anything."""
        form = self._form
        if form is None:
            return
        now = _now(data)
        if key == "escape":
            self._form = None
        elif key == "enter":
            self._submit(form, data)
        elif key in {"tab", "down"}:
            self._form = move(form, 1)
        elif key in {"shift+tab", "up"}:
            self._form = move(form, -1)
        elif key in {"left", "right"}:
            self._form = choose(form, -1 if key == "left" else 1, data, now)
        elif key == "backspace":
            self._form = erase(form)
        elif character is not None and character.isprintable():
            self._form = type_text(form, character)

    def paste(self, text: str) -> None:
        """Add pasted `text` to the current text field."""
        if self._form is not None:
            self._form = type_text(self._form, text)

    def lines(self, data: BoardData, width: int) -> list[StyledLine] | None:
        """The form's lines at `width`, or `None` when it is closed."""
        if self._form is None:
            return None
        return form_lines(self._form, home=_home(data), width=width)

    def content(self, data: BoardData, width: int) -> Content | None:
        """The form in colour, or `None` when it is closed."""
        lines = self.lines(data, width)
        if lines is None:
            return None
        return Content("\n").join(styled_content(line) for line in lines)

    def _submit(self, form: LaunchForm, data: BoardData) -> None:
        action = form_action(form, _home(data))
        error = action if isinstance(action, str) else _try(self._launch, action)
        self._form = None if error is None else replace(form, error=error)


def _try(launch: Launch, action: LaunchBash | LaunchClaude) -> str | None:
    """Send the launch; the error text when it was refused."""
    try:
        launch(action)
    except MeuteError as error:
        return str(error)
    return None


def _now(data: BoardData) -> datetime:
    return data.now or datetime.now(UTC)


def _home(data: BoardData) -> Path:
    return data.home or Path.home()
