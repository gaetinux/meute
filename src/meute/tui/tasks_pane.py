"""The Tasks tab's panes drawn as Textual `Content`: never markup, so data shows literally."""

from textual.content import Content

from meute.core.styled import Role, Span, StyledLine
from meute.core.tasks_view import TaskGroupLine, TaskLine, TasksView
from meute.tui.sessions_pane import (
    BAND_STYLE,
    BLURRED_SELECTED_STYLE,
    SELECTED_STYLE,
    styled_content,
)


def tasks_content(view: TasksView, selected: int, *, focused: bool, width: int) -> Content:
    """Return the task lines in colour, the band lines on red and the selected one on blue
    (grey while the board does not have the focus), padded to `width` so the background spans.
    """
    highlight = SELECTED_STYLE if focused else BLURRED_SELECTED_STYLE
    contents: list[Content] = []
    for index, line in enumerate(view.lines):
        content = styled_content(line.spans)
        band = isinstance(line, TaskGroupLine | TaskLine) and line.band
        if index == selected or band:
            content = content.pad_right(max(width - content.cell_length, 0))
            content = content.stylize(highlight if index == selected else BAND_STYLE)
        contents.append(content)
    return Content("\n").join(contents)


def rows_content(rows: list[StyledLine]) -> Content:
    """Return styled `rows` one under the other."""
    return Content("\n").join(styled_content(row) for row in rows)


def rule(width: int) -> StyledLine:
    """Return a dim horizontal rule `width` columns wide."""
    return (Span("─" * width, Role.DIM),)
