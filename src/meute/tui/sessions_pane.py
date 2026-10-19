"""The board's panes drawn as Textual `Content`: never markup, so data shows literally."""

from datetime import tzinfo

from textual.content import Content

from meute.core.board_sessions import BoardSessions, risky_mode_span
from meute.core.quota_view import QuotaLine, quota_level, quota_lines
from meute.core.sessions_view import SessionInfo, details_lines

SELECTED_STYLE = "reverse"
BLURRED_SELECTED_STYLE = "on #444444"
TITLE_STYLE = "bold reverse"
RISKY_MODE_STYLE = "darkorange"
_LEVEL_STYLES = {"ok": "green", "warn": "yellow", "high": "bold red"}
_LABEL = len("5h ")


def title_content(title: str, *, focused: bool) -> Content:
    """Return the board's title, reversed while the board has the focus."""
    content = Content(f" {title} ")
    return content.stylize(TITLE_STYLE) if focused else content


def view_content(board: BoardSessions, selected: int, *, focused: bool = True) -> Content:
    """Return the view lines, risky permission modes in orange and the selected one
    reversed, or on grey while the board does not have the focus."""
    lines: list[Content] = []
    for index, line in enumerate(board.view.lines):
        content = Content(line.text)
        span = risky_mode_span(board, index)
        if span is not None:
            content = content.stylize(RISKY_MODE_STYLE, *span)
        if index == selected:
            content = content.stylize(SELECTED_STYLE if focused else BLURRED_SELECTED_STYLE)
        lines.append(content)
    return Content("\n").join(lines)


def quota_content(line: QuotaLine, local: tzinfo) -> Content:
    """Return the quota lines, each percentage coloured by its level."""
    lines: list[Content] = []
    for text in quota_lines(line, local=local):
        content = Content(text)
        pct = (
            line.five_hour_pct
            if text.startswith("5h ")
            else line.seven_day_pct
            if text.startswith("7d ")
            else None
        )
        if pct is not None:
            style = _LEVEL_STYLES[quota_level(pct)]
            content = content.stylize(style, _LABEL, text.index("%") + 1)
        lines.append(content)
    return Content("\n").join(lines)


def details_content(board: BoardSessions, info: SessionInfo) -> Content:
    """Return the detail lines of the selected session."""
    return Content("\n".join(details_lines(info, now=board.now, home=board.data.home)))
