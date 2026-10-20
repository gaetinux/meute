"""The board's panes drawn as Textual `Content`: never markup, so data shows literally."""

from collections.abc import Iterable, Mapping
from datetime import tzinfo

from textual.content import Content

from meute.core.board_sessions import BoardSessions
from meute.core.quota_view import QuotaLine, quota_bar_lines
from meute.core.session_details import details_card
from meute.core.sessions_view import CardLine, SessionInfo, SessionLine
from meute.core.styled import Role, StyledLine, title_rule

ROLE_STYLES: Mapping[Role, str] = {
    Role.TITLE: "bold #f2f2f2",
    Role.DIM: "#8a8a8a",
    Role.ACCENT: "#3b8eea",
    Role.KIND: "#4fc1e9",
    Role.RUNNING: "#23d18b",
    Role.IDLE: "#8a8a8a",
    Role.ATTENTION: "bold #f16c6c",
    Role.RISKY: "#e8912d",
    Role.OK: "#23d18b",
    Role.WARN: "#e5c07b",
    Role.HIGH: "bold #f16c6c",
    Role.LATE: "#f16c6c",
    Role.BLOCKED: "#e8912d",
    Role.REVIEW: "#c678dd",
    Role.TAB_ACTIVE: "bold #0c0c0c on #3b8eea",
    Role.TAB: "#8a8a8a",
    Role.PLAIN: "",
}
BAND_STYLE = "on #4a1c22"
SELECTED_STYLE = "on #264f78"
BLURRED_SELECTED_STYLE = "on #444444"
_BLURRED_TAB_STYLE = f"{ROLE_STYLES[Role.TAB]} underline"


def styled_content(line: StyledLine) -> Content:
    """Return `line` with each segment in the style of its role."""
    return Content.assemble(*((span.text, ROLE_STYLES[span.role]) for span in line))


def tabs_content(line: StyledLine, *, focused: bool) -> Content:
    """Return the tabs line; without the focus the active tab is underlined, not filled."""
    if focused:
        return styled_content(line)
    parts = (
        (span.text, _BLURRED_TAB_STYLE if span.role is Role.TAB_ACTIVE else ROLE_STYLES[span.role])
        for span in line
    )
    return Content.assemble(*parts)


def highlighted_content(
    lines: Iterable[tuple[StyledLine, bool, bool]], *, focused: bool, width: int
) -> Content:
    """Return `(line, selected, band)` rows in colour: selected ones on blue (grey while the
    board does not have the focus), band ones on red, both padded to `width` so the
    background spans the board.
    """
    highlight = SELECTED_STYLE if focused else BLURRED_SELECTED_STYLE
    contents: list[Content] = []
    for line, selected, band in lines:
        content = styled_content(line)
        if selected or band:
            content = content.pad_right(max(width - content.cell_length, 0))
            content = content.stylize(highlight if selected else BAND_STYLE)
        contents.append(content)
    return Content("\n").join(contents)


def view_content(
    board: BoardSessions, selected: int, *, focused: bool = True, width: int = 0
) -> Content:
    """Return the view lines in colour, the band lines on red and the selected session's
    card (all its lines) on blue, or on grey while the board does not have the focus.

    Lines on a background are padded to `width` so that the background spans the board.
    """
    lines = board.view.lines
    current = lines[selected] if 0 <= selected < len(lines) else None
    chosen = current.session_id if isinstance(current, SessionLine) else None
    rows = (
        (
            line.spans,
            index == selected or (isinstance(line, CardLine) and line.session_id == chosen),
            line.band,
        )
        for index, line in enumerate(lines)
    )
    return highlighted_content(rows, focused=focused, width=width)


def quota_content(line: QuotaLine, local: tzinfo, width: int) -> Content:
    """Return the quota lines with their bars, coloured by level, then a dim rule `width` wide."""
    rows = [*quota_bar_lines(line, local=local), title_rule(None, width, Role.DIM)]
    return Content("\n").join(styled_content(row) for row in rows)


def details_content(board: BoardSessions, info: SessionInfo, width: int) -> Content:
    """Return the details of the selected session: a rule with its title, then a few rows."""
    rows = details_card(info, home=board.data.home, width=width)
    return Content("\n").join(styled_content(row) for row in rows)
