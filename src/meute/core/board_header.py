"""The tabs line of the board and the totals shown at its right."""

from enum import Enum, auto

from meute.core.sessions_view_text import duration_text
from meute.core.styled import Role, Span, StyledLine, fit


class Tab(Enum):
    """The two tabs of the board."""

    SESSIONS = auto()
    TASKS = auto()


def tabs_line(active: Tab, *, overdue: int, totals: str, width: int) -> StyledLine:
    """Return the tabs line: both tabs, the overdue count when positive, `totals` at the right."""
    left: list[Span] = [
        Span(" Sessions ", Role.TAB_ACTIVE if active is Tab.SESSIONS else Role.TAB),
        Span(" Tasks ", Role.TAB_ACTIVE if active is Tab.TASKS else Role.TAB),
    ]
    if overdue > 0:
        left.append(Span(f" {overdue}!", Role.HIGH))
    return fit(tuple(left), (Span(totals, Role.DIM),), width)


def sessions_totals(live: int, duration_ms: int | None, cost: float | None) -> str:
    """Return `{live} live`, then the duration and the cost when known."""
    text = f"{live} live"
    if duration_ms is not None:
        text += f" · {duration_text(duration_ms)}"
    if cost is not None:
        text += f" · ${cost:.2f}"
    return text


def tasks_totals(open_: int, overdue: int) -> str:
    """Return `{open} open · {overdue} overdue`; the overdue part is omitted at 0."""
    text = f"{open_} open"
    return f"{text} · {overdue} overdue" if overdue > 0 else text
