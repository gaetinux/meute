"""The tabs line of the board and the totals shown at its right."""

from enum import Enum, auto

from meute.core.board_view import BoardData
from meute.core.session_state import is_live
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


def tab_at(line: StyledLine, x: int) -> Tab | None:
    """Return the tab whose name covers column `x` of a tabs `line`, or `None`."""
    names = iter(Tab)
    start = 0
    for span in line:
        end = start + len(span.text)
        if span.role in {Role.TAB, Role.TAB_ACTIVE}:
            tab = next(names, None)
            if start <= x < end:
                return tab
        start = end
    return None


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


def board_totals(data: BoardData) -> str:
    """Return the Sessions totals: live sessions, summed duration and cost of those reporting."""
    live = sum(1 for row in data.sessions if is_live(row.session.state))
    reported = [
        data.metrics[row.session.id] for row in data.sessions if row.session.id in data.metrics
    ]
    durations = [m.duration_ms for m in reported if m.duration_ms is not None]
    costs = [m.cost_usd for m in reported if m.cost_usd is not None]
    return sessions_totals(
        live, sum(durations) if durations else None, sum(costs) if costs else None
    )
