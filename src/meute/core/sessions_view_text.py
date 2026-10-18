"""Texts of the Sessions view: lines, headers and the details of one session."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from meute.core.attention import needs_attention
from meute.core.board_view import SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.paths import display_path
from meute.core.session_state import is_live, state_label
from meute.core.statusline import StatuslineData
from meute.core.text import one_line, printable

_DISPLAYED_MARK = "▶ "
_NOT_DISPLAYED_MARK = "  "
_MIN_COST = 0.10  # like the statusline: a smaller cost is noise
_MAX_REPLY = 200
_MINUTE = 60
_HOUR = 3600
_DAY = 86400


@dataclass(frozen=True, slots=True, kw_only=True)
class SessionInfo:
    """A session with what Claude and its statusline reported, and the group it is shown in."""

    row: SessionRow
    details: ClaudeDetails | None
    metrics: StatuslineData | None
    group: str


def age_text(then: datetime, now: datetime) -> str:
    """Return how long ago `then` was: `now`, `{m}m`, `{h}h` or `{d}d`."""
    seconds = (now - then).total_seconds()
    if seconds < _MINUTE:
        return "now"
    if seconds < _HOUR:
        return f"{int(seconds // _MINUTE)}m"
    if seconds < _DAY:
        return f"{int(seconds // _HOUR)}h"
    return f"{int(seconds // _DAY)}d"


def duration_text(milliseconds: int) -> str:
    """Return a duration as `{h}h{mm}` or, under an hour, `{m}m`."""
    minutes = max(milliseconds, 0) // 1000 // _MINUTE
    hours, rest = divmod(minutes, 60)
    return f"{hours}h{rest:02d}" if hours else f"{minutes}m"


def session_text(info: SessionInfo, *, now: datetime) -> str:
    """Return the line of a session: marks, title, state, age, then what is known."""
    session = info.row.session
    mark = _DISPLAYED_MARK if info.row.displayed else _NOT_DISPLAYED_MARK
    attention = "!" if needs_attention(session.state) else " "
    parts = [
        printable(session.title),
        state_label(session.state),
        age_text(session.last_activity_at, now),
    ]
    metrics = info.metrics
    if metrics is not None and metrics.context_pct is not None:
        parts.append(f"{metrics.context_pct:.0f}%")
    if metrics is not None and metrics.cost_usd is not None and metrics.cost_usd > _MIN_COST:
        parts.append(f"${metrics.cost_usd:.2f}")
    mode = info.details.permission_mode if info.details is not None else None
    if mode:
        parts.append(f"[{one_line(mode, _MAX_REPLY)}]")
    return f"{mark}{attention}" + "  ".join(parts)


def header_text(group: str, members: Sequence[SessionInfo]) -> str:
    """Return a group header: its name, live sessions, total duration and cost when known."""
    live = sum(1 for info in members if is_live(info.row.session.state))
    durations = [m.duration_ms for info in members if (m := info.metrics) and m.duration_ms]
    costs = [m.cost_usd for info in members if (m := info.metrics) and m.cost_usd is not None]
    parts = [f"{live} live"]
    if durations:
        parts.append(duration_text(sum(durations)))
    if costs:
        parts.append(f"${sum(costs):.2f}")
    return f"{printable(group)}  " + " · ".join(parts)


def details_lines(info: SessionInfo, *, now: datetime, home: Path | None) -> list[str]:  # noqa: ARG001 — the signature is shared with the other views
    """Return the detail lines of the selected session; unknown parts are left out."""
    session = info.row.session
    details = info.details or ClaudeDetails()
    metrics = info.metrics or StatuslineData()
    lines = [f"Folder: {printable(display_path(session.cwd, home))}"]
    known = (
        ("Model", details.model),
        ("Mode", details.permission_mode),
        ("Waiting for", details.pending_permission),
        ("Last tool", details.last_tool),
    )
    lines += [f"{label}: {one_line(value, _MAX_REPLY)}" for label, value in known if value]
    if details.last_message:
        lines.append(f"Last reply: {one_line(details.last_message, _MAX_REPLY)}")
    if metrics.context_pct is not None:
        lines.append(f"Context: {metrics.context_pct:.0f}%")
    if metrics.cost_usd is not None:
        lines.append(f"Cost: ${metrics.cost_usd:.2f}")
    if metrics.duration_ms is not None:
        lines.append(f"Duration: {duration_text(metrics.duration_ms)}")
    return lines
