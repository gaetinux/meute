"""A one-line input and a short choice list, hidden until something must be typed or picked."""

from dataclasses import dataclass
from typing import ClassVar, assert_never

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Input, OptionList, Static

PROMPT_MARK = "\u203a "  # a single right-pointing angle quote


@dataclass(frozen=True, slots=True, kw_only=True)
class TextAsk:
    """Ask for one line of text after `label`, starting from `value`."""

    label: str
    value: str = ""


@dataclass(frozen=True, slots=True, kw_only=True)
class ChoiceAsk:
    """Ask to pick one of `choices`, starting on `highlighted`."""

    choices: tuple[str, ...]
    highlighted: int = 0


Ask = TextAsk | ChoiceAsk


class TaskInput(Vertical):
    """The line (mark, label, input, a preview under it) or the list; one shows at a time.

    The board receives `Input.Changed`, `Input.Submitted` and `OptionList.OptionSelected`.
    """

    DEFAULT_CSS: ClassVar[str] = """
    TaskInput { height: auto; display: none; }
    TaskInput #input-row { height: 1; }
    TaskInput #input-label { width: auto; }
    TaskInput Input, TaskInput Input:focus { border: none; height: 1; padding: 0; width: 1fr; }
    TaskInput #input-preview { height: auto; }
    TaskInput OptionList, TaskInput OptionList:focus { height: auto; border: none; padding: 0; }
    """

    def __init__(self) -> None:
        super().__init__(id="task-input")
        self._label = Static(id="input-label")
        self._line = Input(id="input-line", select_on_focus=False)
        self._row = Horizontal(self._label, self._line, id="input-row")
        self._preview = Static(id="input-preview")
        self._choices = OptionList(id="input-choices")

    def compose(self) -> ComposeResult:
        yield self._row
        yield self._preview
        yield self._choices

    @property
    def is_open(self) -> bool:
        """Whether the line or the list is shown."""
        return self.display

    def open(self, ask: Ask) -> None:
        """Show what `ask` needs, give it the focus, and hide the preview."""
        self.display = True
        self._preview.display = False
        match ask:
            case TextAsk(label=label, value=value):
                self._label.update(Content(PROMPT_MARK + label))
                self._line.value = value
                self._line.cursor_position = len(value)
                self._row.display, self._choices.display = True, False
                self._line.focus()
            case ChoiceAsk(choices=choices, highlighted=highlighted):
                self._choices.clear_options()
                _ = self._choices.add_options([Content(choice) for choice in choices])
                self._choices.highlighted = highlighted
                self._row.display, self._choices.display = False, True
                self._choices.focus()
            case _:
                assert_never(ask)

    def show_preview(self, preview: Content) -> None:
        """Show `preview` under the line."""
        self._preview.update(preview)
        self._preview.display = True

    def close(self) -> None:
        """Hide everything and give the focus back to the board."""
        self.display = False
        self.screen.set_focus(None)
