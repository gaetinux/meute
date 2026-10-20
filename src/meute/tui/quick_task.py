"""The `M-t` window: a small app, run in a tmux popup, that notes one task from anywhere."""

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Protocol

from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Input, Static

from meute.core.errors import MeuteError
from meute.core.project import ProjectRef
from meute.core.quick_preview import PreviewError, QuickPreview, preview_lines, quick_preview
from meute.core.styled import Role, Span, StyledLine
from meute.core.task import Task
from meute.core.text import one_line, printable
from meute.tui.sessions_pane import ROLE_STYLES
from meute.tui.task_input import TaskInput, TextAsk
from meute.tui.tasks_pane import rows_content

_PROJECT_WIDTH = 40


@dataclass(frozen=True, slots=True, kw_only=True)
class QuickContext:
    """What the preview needs: the clock, the displayed session's project and all projects."""

    now: datetime
    default: ProjectRef | None
    projects: tuple[ProjectRef, ...]


class QuickTaskBackend(Protocol):
    """Where the window reads its context and creates the task."""

    def context(self) -> QuickContext:
        """Return the clock and the projects the preview resolves against."""
        ...

    def create(self, text: str) -> Task:
        """Create the task the quick entry `text` describes.

        Raises:
            MeuteError: nothing was created.
        """
        ...


class QuickTaskApp(App[None]):
    """A frame with a header, the quick-entry line and its live preview.

    Enter creates the task and exits with code 0; Esc exits without writing anything. An
    entry that cannot be created, or a failed creation, keeps the window open with the text.
    """

    CSS: ClassVar[str] = """
    #frame { border: solid #3b8eea; height: 100%; padding: 0 1; }
    #frame.failed { border: solid #f16c6c; }
    #header { height: 1; }
    #header-title { width: 1fr; }
    #header-project { width: auto; }
    TaskInput { margin-top: 1; }
    """
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", show=False, priority=True),
    ]

    def __init__(self, backend: QuickTaskBackend) -> None:
        super().__init__()
        self._backend = backend
        self._quick = backend.context()
        self._input = TaskInput()
        self._failure: str | None = None

    def compose(self) -> ComposeResult:
        default = self._quick.default
        project = "floating" if default is None else f"in {one_line(default.name, _PROJECT_WIDTH)}"
        with Vertical(id="frame"):
            with Horizontal(id="header"):
                yield Static(
                    Content.styled("New task", ROLE_STYLES[Role.ACCENT]), id="header-title"
                )
                yield Static(Content.styled(project, ROLE_STYLES[Role.DIM]), id="header-project")
            yield self._input

    async def on_event(self, event: events.Event) -> None:
        """Drop Alt keys: the line types none, and the key that opened the window would
        otherwise type its letter when pressed again (tmux hands it to the window)."""
        if isinstance(event, events.Key) and event.key.startswith("alt+"):
            event.stop()
            return
        await super().on_event(event)

    def on_mount(self) -> None:
        self._input.open(TextAsk(label=""))
        self._show("")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._failure = None
        self._show(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        preview = self._preview(event.value)
        if not preview.can_create:
            self._failure = preview.error or PreviewError.EMPTY_TITLE
        else:
            try:
                _ = self._backend.create(event.value)
            except MeuteError as error:
                self._failure = str(error)
            else:
                self.exit(return_code=0)
                return
        self._show(event.value)

    def action_cancel(self) -> None:
        self.exit(return_code=0)

    def _preview(self, text: str) -> QuickPreview:
        context = self._quick
        return quick_preview(
            text, now=context.now, default=context.default, projects=context.projects
        )

    def _show(self, text: str) -> None:
        preview = self._preview(text)
        lines = preview_lines(preview, self._quick.now)
        middle: StyledLine = (
            ()
            if self._failure is None
            else (Span(f"Error: {printable(self._failure)}", Role.HIGH),)
        )
        self._input.show_preview(rows_content([(), *lines[:-1], middle, lines[-1]]))
        failed = self._failure is not None or preview.error is not None
        _ = self.query_one("#frame", Vertical).set_class(failed, "failed")
