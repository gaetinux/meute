"""The Tasks tab's panes drawn as Textual `Content`: never markup, so data shows literally."""

from textual.content import Content

from meute.core.styled import Role, StyledLine, title_rule
from meute.core.tasks_view import TaskGroupLine, TaskLine, TasksView
from meute.tui.sessions_pane import highlighted_content, styled_content


def tasks_content(view: TasksView, selected: int, *, focused: bool, width: int) -> Content:
    """Return the task lines in colour, the band lines on red and the selected one on blue
    (grey while the board does not have the focus), padded to `width` so the background spans.
    """
    rows = (
        (line.spans, index == selected, isinstance(line, TaskGroupLine | TaskLine) and line.band)
        for index, line in enumerate(view.lines)
    )
    return highlighted_content(rows, focused=focused, width=width)


def rows_content(rows: list[StyledLine]) -> Content:
    """Return styled `rows` one under the other."""
    return Content("\n").join(styled_content(row) for row in rows)


def rule(width: int) -> StyledLine:
    """Return a dim horizontal rule `width` columns wide."""
    return title_rule(None, width, Role.DIM)
