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
from meute.core.launch_form_worktree import with_worktrees
from meute.core.styled import StyledLine
from meute.tui.board_types import BoardGit
from meute.tui.sessions_pane import styled_content

Launch = Callable[[LaunchBash | LaunchClaude], None]
# Starts a launch on a task in a worker, which tells its error (or None) when it ends;
# `False` when it did not start: a launch on that task already runs.
LaunchTask = Callable[[LaunchClaude, Callable[[str | None], None]], bool]


class LaunchFormPanel(Static):
    """The form's lines, above the footer; hidden while the form is closed."""

    DEFAULT_CSS = "LaunchFormPanel { height: auto; display: none; }"

    def __init__(self) -> None:
        super().__init__(id="launch-form")


class FormSession:
    """The form while it is open: it takes every key, and a launch that fails keeps it.

    A launch with a task waits for Claude in a worker: meanwhile the form stays as it is and
    ignores every key and paste.
    """

    def __init__(
        self, *, launch: Launch, launch_task: LaunchTask, default_mode: str, git: BoardGit | None
    ) -> None:
        self._launch = launch
        self._launch_task = launch_task
        self._default_mode = default_mode
        self._git = git
        self._form: LaunchForm | None = None
        self._waiting = False  # a launch with a task runs in a worker

    @property
    def is_open(self) -> bool:
        """Whether the form is open."""
        return self._form is not None

    def open(self, data: BoardData, entry: BoardEntry | None) -> None:
        """Open the form on the selected `entry`."""
        form = open_form(data, entry, default_mode=self._default_mode, now=_now(data))
        self._form = self._listed(form)

    def refresh(self, data: BoardData) -> None:
        """Take a new reading of the board: only the busy folders change."""
        if self._form is not None:
            self._form = with_busy(self._form, data)

    def key(self, key: str, character: str | None, data: BoardData) -> None:
        """Apply `key` to the open form; `character` is what the key types, if anything."""
        form = self._form
        if form is None or self._waiting:
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
            chosen = choose(form, -1 if key == "left" else 1, data, now)
            self._form = chosen if chosen.repo == form.repo else self._listed(chosen)
        elif key == "backspace":
            self._form = erase(form)
        elif character is not None and character.isprintable():
            self._form = type_text(form, character)

    def paste(self, text: str) -> None:
        """Add pasted `text` to the current text field."""
        if self._form is not None and not self._waiting:
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

    def _listed(self, form: LaunchForm) -> LaunchForm:
        """Return `form` with the worktrees its repository has, as `git` lists them."""
        if form.repo is None or self._git is None:
            return form
        return with_worktrees(form, self._git.worktrees(form.repos[form.repo].path))

    def _submit(self, form: LaunchForm, data: BoardData) -> None:
        action = form_action(form, _home(data))
        if isinstance(action, LaunchClaude) and action.task_id is not None:
            self._waiting = self._launch_task(action, self._ended)
            return
        error = action if isinstance(action, str) else _try(self._launch, action)
        self._ended(error)

    def _ended(self, error: str | None) -> None:
        """The launch ended: the form closes, or keeps its text and shows the error."""
        self._waiting = False
        if self._form is not None:
            self._form = None if error is None else replace(self._form, error=error)


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
