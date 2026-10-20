"""The details of the selected session under the list: a rule with its title, then a few rows."""

from pathlib import Path

from meute.core.claude_session import ClaudeDetails
from meute.core.paths import display_path
from meute.core.sessions_view_text import SessionInfo, clip
from meute.core.styled import Role, Span, StyledLine
from meute.core.text import one_line, printable

_MAX_VALUE = 200
_LABEL_WIDTH = 12
_RULE = "─"


def _rule(title: str, width: int) -> StyledLine:
    """Return `─ {title} ───…`, `width` columns wide (cut when the title is longer)."""
    head = f"{_RULE} {one_line(title, _MAX_VALUE)} "
    return clip((Span(head + _RULE * max(width - len(head), 0), Role.ACCENT),), width)


def _row(label: str, value: str, width: int) -> StyledLine:
    padded = label.ljust(_LABEL_WIDTH)
    return clip((Span(padded, Role.DIM), Span(one_line(value, _MAX_VALUE))), width)


def details_card(info: SessionInfo, *, home: Path | None, width: int) -> list[StyledLine]:
    """Return the rule and the rows `Reply`, `Folder` and `Waiting for` (when known)."""
    session = info.row.session
    details = info.details or ClaudeDetails()
    rows = (
        ("Reply", details.last_message),
        ("Folder", printable(display_path(session.cwd, home))),
        ("Waiting for", details.pending_permission),
    )
    return [_rule(session.title, width), *(_row(k, v, width) for k, v in rows if v)]
