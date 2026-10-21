"""The details of the selected session under the list: a rule with its title, then a few rows."""

from pathlib import Path

from meute.core.claude_session import ClaudeDetails
from meute.core.paths import display_path
from meute.core.sessions_view_text import SessionInfo
from meute.core.styled import Role, Span, StyledLine, clip, labelled, title_rule
from meute.core.text import one_line, printable

_MAX_VALUE = 200
_LABEL_WIDTH = 12


def _row(label: str, value: str, width: int) -> StyledLine:
    return clip(labelled(label, _LABEL_WIDTH, Span(one_line(value, _MAX_VALUE))), width)


def details_card(info: SessionInfo, *, home: Path | None, width: int) -> list[StyledLine]:
    """Return the rule and the rows `Reply`, `Folder` and `Waiting for` (when known)."""
    session = info.row.session
    details = info.details or ClaudeDetails()
    rows = (
        ("Reply", details.last_message),
        ("Folder", printable(display_path(session.cwd, home))),
        ("Waiting for", details.pending_permission),
    )
    rule = title_rule(one_line(session.title, _MAX_VALUE), width, Role.ACCENT)
    return [rule, *(_row(k, v, width) for k, v in rows if v)]
