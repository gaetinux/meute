"""Where the keys and pastes go while an input is open: the task input or the launch form."""

from collections.abc import Callable
from typing import Protocol

from textual import events


class _Editor(Protocol):
    @property
    def editing(self) -> bool: ...

    def cancel(self) -> None: ...


class _Form(Protocol):
    @property
    def form_open(self) -> bool: ...

    def form_key(self, key: str, character: str | None) -> None: ...

    def form_paste(self, text: str) -> None: ...


class OpenInputs:
    """Takes the keys of an open input: none reaches the controllers, a click does not leave it.

    The task input takes every key but Escape, which cancels it; the launch form takes
    them all and applies them itself.
    """

    def __init__(self, editor: _Editor, form: _Form, reset: Callable[[], None]) -> None:
        self._editor = editor
        self._form = form
        self._reset = reset

    @property
    def is_open(self) -> bool:
        """Whether an input is open."""
        return self._editor.editing or self._form.form_open

    def key(self, event: events.Key) -> bool:
        """Apply `event` to the open input; `False` when no input is open."""
        if self._editor.editing:
            if event.key in {"tab", "shift+tab"}:
                event.prevent_default()  # the focus stays in the input
            elif event.key == "escape":
                self._reset()
                self._editor.cancel()
            return True
        if self._form.form_open:
            event.prevent_default()
            event.stop()
            self._reset()
            self._form.form_key(event.key, event.character)
            return True
        return False

    def paste(self, text: str) -> bool:
        """Add pasted `text` to the open launch form; `False` when it is not open."""
        if self._editor.editing or not self._form.form_open:
            return False
        self._form.form_paste(text)
        return True
