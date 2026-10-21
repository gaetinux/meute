"""Texts of the Sessions view: card lines, group headers, sections and a session's details."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import assert_never

from meute.core.board_view import SessionRow
from meute.core.claude_session import ClaudeDetails
from meute.core.paths import display_path
from meute.core.quota_view import level_role
from meute.core.session_state import (
    Compacting,
    Exited,
    Idle,
    MaybeStuck,
    PermissionRequested,
    Running,
    SessionState,
    SubagentRunning,
    Unknown,
    Unreachable,
    WaitingInput,
    is_live,
    state_label,
)
from meute.core.statusline import StatuslineData
from meute.core.styled import Role, Span, StyledLine, clip, fit, fold_mark, plain
from meute.core.text import cost_text, one_line, printable

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


RISKY_MODES = frozenset({"auto", "bypassPermissions", "dontAsk"})
"""Permission modes in which Claude acts without asking (spec 6.2): shown in orange."""

_SEPARATOR = " · "
_CARD_INDENT = "    "


def attention_reason(info: SessionInfo) -> str:
    """Return why a session waits for the user: the permission it asks, a reply, or stuck."""
    state = info.row.session.state
    match state:
        case PermissionRequested():
            tool = info.details.pending_permission if info.details is not None else None
            return f"permission: {one_line(tool, _MAX_REPLY)}" if tool else "permission requested"
        case WaitingInput():
            return "waiting for your reply"
        case MaybeStuck():
            return "stuck?"
        case (
            Running()
            | SubagentRunning()
            | Compacting()
            | Idle()
            | Exited()
            | Unreachable()
            | Unknown()
        ):
            return state_label(state)
        case _:
            assert_never(state)


def state_role(state: SessionState) -> Role:
    """Return the role of a session card symbol: attention, at work, or idle or ended."""
    match state:
        case PermissionRequested() | WaitingInput() | MaybeStuck():
            return Role.ATTENTION
        case Running() | SubagentRunning() | Compacting():
            return Role.RUNNING
        case Idle() | Exited() | Unreachable() | Unknown():
            return Role.IDLE
        case _:
            assert_never(state)


STATE_SYMBOLS = {Role.ATTENTION: "!", Role.RUNNING: "●", Role.IDLE: "○"}


def _with_title(
    head: StyledLine, title: str, role: Role, tail: StyledLine, width: int
) -> StyledLine:
    """Return `head`, the title shortened to leave room for `tail`, then `tail`."""
    room = width - len(plain(head)) - len(plain(tail))
    if room < 1:
        return clip((*head, Span(one_line(title, _MAX_REPLY), role), *tail), width)
    return (*head, Span(one_line(title, room, ellipsis=True), role), *tail)


def _head(info: SessionInfo, symbol: str, role: Role) -> StyledLine:
    """Return `  {symbol} `, with `▶` for the first space on the session shown in the pane."""
    if info.row.displayed:
        return (Span("▶", Role.ACCENT), Span(f" {symbol} ", role))
    return (Span(f"  {symbol} ", role),)


def card_first_line(info: SessionInfo, *, now: datetime, width: int) -> StyledLine:
    """Return `  {sym} {title}  {state}  {age}`: the line of a session in its group."""
    session = info.row.session
    role = state_role(info.row.session.state)
    age = age_text(session.last_activity_at, now)
    tail = (
        Span("  "),
        Span(state_label(session.state), role),
        Span("  " + (age if age == "now" else f"{age} ago"), Role.DIM),
    )
    head = _head(info, STATE_SYMBOLS[role], role)
    return _with_title(head, session.title, Role.TITLE, tail, width)


def needs_you_first_line(info: SessionInfo, *, width: int) -> StyledLine:
    """Return `  ! {title} · {group} · {reason}`: the line of a session in "Needs you"."""
    tail = (
        Span(f"{_SEPARATOR}{printable(info.group)}{_SEPARATOR}", Role.DIM),
        Span(attention_reason(info), Role.ATTENTION),
    )
    head = _head(info, "!", Role.ATTENTION)
    return _with_title(head, info.row.session.title, Role.TITLE, tail, width)


def ref_line(info: SessionInfo, *, width: int) -> StyledLine:
    """Return `  ! {title}  ↑ needs you`: where a session in "Needs you" sits in its group."""
    head = (Span("  ! ", Role.ATTENTION),)
    tail = (Span("  ↑ needs you", Role.DIM),)
    return _with_title(head, info.row.session.title, Role.DIM, tail, width)


def _joined(parts: Sequence[Span], prefix: str, width: int) -> StyledLine | None:
    if not parts:
        return None
    line: list[Span] = [Span(prefix, Role.DIM)]
    for index, part in enumerate(parts):
        if index:
            line.append(Span(_SEPARATOR, Role.DIM))
        line.append(part)
    return clip(tuple(line), width)


def _metrics_parts(details: ClaudeDetails, metrics: StatuslineData) -> list[Span]:
    parts: list[Span] = []
    if metrics.duration_ms is not None:
        parts.append(Span(duration_text(metrics.duration_ms), Role.DIM))
    if cost := cost_text(metrics.cost_usd):
        parts.append(Span(cost, Role.DIM))
    if metrics.context_pct is not None:
        level = level_role(metrics.context_pct)
        parts.append(Span(f"{metrics.context_pct:.0f}%", level))
    if details.model:
        parts.append(Span(one_line(details.model, _MAX_REPLY), Role.DIM))
    if mode := details.permission_mode:
        risky = Role.RISKY if mode in RISKY_MODES else Role.DIM
        parts.append(Span(one_line(mode, _MAX_REPLY), risky))
    return parts


def card_more_lines(info: SessionInfo, *, width: int) -> list[StyledLine]:
    """Return lines 2 and 3 of a card: duration, cost, context, model, mode; branch, tool.

    Unknown parts are left out, and a line with nothing known is omitted.
    """
    details = info.details or ClaudeDetails()
    metrics = info.metrics or StatuslineData()
    where = [
        Span(one_line(text, _MAX_REPLY), Role.DIM)
        for text in (metrics.worktree_branch, details.last_tool)
        if text
    ]
    lines = (
        _joined(_metrics_parts(details, metrics), _CARD_INDENT, width),
        _joined(where, f"{_CARD_INDENT}└ ", width),
    )
    return [line for line in lines if line is not None]


def header_line(  # noqa: PLR0913 — the group, what it shows, and the width
    group: str,
    members: Sequence[SessionInfo],
    *,
    kind: str | None,
    button: bool,
    folded: bool,
    width: int,
) -> StyledLine:
    """Return a group header: `▼ {name} ◆ {kind} · {n} live · {cost}`, `+ session` at right.

    `+ session` shows when `button` is true (the group's repository is known) and the group
    is not folded; a folded group starts with `▶`. Unknown parts and a cost of at most
    10 cents are left out.
    """
    live = sum(1 for info in members if is_live(info.row.session.state))
    costs = [m.cost_usd for info in members if (m := info.metrics) and m.cost_usd is not None]
    cost = cost_text(sum(costs) if costs else None)
    totals = f"{_SEPARATOR}{live} live" + (f"{_SEPARATOR}{cost}" if cost else "")
    left: list[Span] = [Span(f"{fold_mark(folded=folded)} {printable(group)}", Role.TITLE)]
    if kind is not None:
        left.append(Span(f" ◆ {printable(kind)}", Role.KIND))
    left.append(Span(totals, Role.DIM))
    if folded or not button:
        return clip(tuple(left), width)
    return fit(tuple(left), (Span("+ session", Role.RUNNING),), width)


def section_line(title: str, count: int, *, folded: bool) -> StyledLine:
    """Return a bottom section heading: `▼ {title} ({count})`, `▶` when folded."""
    return (Span(f"{fold_mark(folded=folded)} {title} ({count})", Role.DIM),)


def needs_you_heading(title: str, count: int, *, folded: bool) -> StyledLine:
    """Return the heading of "Needs you": `{title} ({count})`, after `▶ ` when folded."""
    mark = f"{fold_mark(folded=True)} " if folded else ""
    return (Span(f"{mark}{title} ({count})", Role.ATTENTION),)


def item_line(text: str, width: int) -> StyledLine:
    """Return an already printable item of a section, indented by two spaces."""
    return clip((Span(f"  {text}"),), width)


def dim_line(text: str, width: int) -> StyledLine:
    """Return an information line in the dim role."""
    return clip((Span(text, Role.DIM),), width)


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
