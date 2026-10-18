"""The status line meute prints: a port of the author's `statusline-command.sh`."""

import re
from collections.abc import Callable, Mapping
from datetime import datetime, tzinfo
from zoneinfo import ZoneInfo

from meute.core.config_validate import QuotasConfig
from meute.core.statusline import StatuslineData
from meute.core.text import printable

_SEP = " \033[90m│\033[0m "
_RESET = "\033[0m"
_ESCAPE = re.compile(r"\033\[[0-9;]*m")
_BAR_CELLS = 5
_WARN_PCT = 50
_ALERT_PCT = 80
_MIN_COST = 0.10
_MIN_DURATION_MS = 600_000
_LAST_WEEKDAY = 5  # Friday, in ISO numbering
_NARROW = 80
_DEFAULT_WIDTH = 200


def _basename(path: str) -> str:
    stripped = path.rstrip("/")
    if not stripped:
        return "/" if path else ""
    return stripped.rpartition("/")[2]


def _bar(pct: int) -> str:
    filled = min(max((pct + 10) * _BAR_CELLS // 100, 0), _BAR_CELLS)
    return "█" * filled + "░" * (_BAR_CELLS - filled)


def _color(pct: int) -> str:
    if pct >= _ALERT_PCT:
        return "31"
    return "33" if pct >= _WARN_PCT else "32"


def _meter(pct: float, label: str) -> str:
    shown = round(pct)  # to the nearest even integer, like printf '%.0f'
    return f"\033[{_color(shown)}m{_bar(shown)}{_RESET} \033[90m{label}{_RESET} {shown}%"


def _cost(cost: float | None) -> str:
    return f"${cost:.2f}" if cost is not None and cost > _MIN_COST else ""


def _duration(milliseconds: int | None) -> str:
    if milliseconds is None or milliseconds <= _MIN_DURATION_MS:
        return ""
    minutes = milliseconds // 1000 // 60
    hours, rest = divmod(minutes, 60)
    text = f"{hours}h{rest:02d}m" if hours else f"{minutes}m"
    return f"\033[90m{text}{_RESET}"


def _lines(added: int | None, removed: int | None) -> str:
    if (added or 0) + (removed or 0) <= 0:
        return ""
    parts: list[str] = []
    if added is not None and added > 0:
        parts.append(f"\033[32m+{added}{_RESET}")
    if removed is not None and removed > 0:
        parts.append(f"\033[31m-{removed}{_RESET}")
    return " ".join(parts)


def _name(name: str | None) -> str:
    return f"\033[36m{printable(name)}{_RESET}" if name else ""


def _peak(now: datetime, quotas: QuotasConfig, local: tzinfo) -> str:
    there = now.astimezone(ZoneInfo(quotas.peak_timezone))
    hour = there.hour
    weekday = there.isoweekday()
    start, end = quotas.peak_start_hour, quotas.peak_end_hour
    if weekday <= _LAST_WEEKDAY and start <= hour < end:
        return f"\033[1;31m⚡ PEAK{_RESET} \033[90m(~{end - hour}h left){_RESET}"
    off = f"\033[1;32m✦ OFF-PEAK{_RESET} \033[90m"
    if weekday > _LAST_WEEKDAY or (weekday == _LAST_WEEKDAY and hour >= end):
        return f"{off}(weekend){_RESET}"
    if hour >= end:
        local_start = there.replace(hour=start % 24, minute=0, second=0).astimezone(local).hour
        return f"{off}(until {local_start}h){_RESET}"
    return f"{off}(peak in ~{start - hour}h){_RESET}"


def _visible_length(text: str) -> int:
    return len(_ESCAPE.sub("", text))


def _join(segments: list[str]) -> str:
    return _SEP.join(segment for segment in segments if segment)


def _fit(base: list[str], candidates: list[str], width: int) -> str:
    """Add each non-empty candidate to `base`, in order, when the line still fits."""
    line = _join(base)
    for candidate in candidates:
        if candidate and _visible_length(f"{line}{_SEP}{candidate}") <= width:
            line = f"{line}{_SEP}{candidate}"
    return line


def render_statusline(  # noqa: PLR0913 — every input is a keyword of the documented interface
    data: StatuslineData,
    *,
    user: str,
    now: datetime,
    quotas: QuotasConfig,
    local: tzinfo,
    width: int,
) -> str:
    """Return the status line for `data`, folded to fit `width` visible characters.

    Everything Claude sent is made printable first, so it cannot inject escape sequences.
    `now` is any aware instant; the peak hours are read in `quotas.peak_timezone` and the
    start of the peak is told in the `local` zone.
    """
    header = (
        f"\033[1;32m➜{_RESET} \033[1m{printable(user)}{_RESET} "
        f"\033[36m{printable(_basename(data.cwd) if data.cwd is not None else '~')}{_RESET}"
    )
    model = f"\033[35m{printable(data.model_name or 'Claude')}{_RESET}"
    five = "" if data.five_hour_pct is None else _meter(data.five_hour_pct, "5h")
    always = [header, model, five, _peak(now, quotas, local)]
    context = "" if data.context_pct is None else _meter(data.context_pct, "ctx")
    cost = _cost(data.cost_usd)
    worktree = _name(data.worktree_name)
    agent = _name(data.agent_name)
    seven = ""
    if data.seven_day_pct is not None and round(data.seven_day_pct) > _WARN_PCT:
        seven = _meter(data.seven_day_pct, "7d")
    tier_three = [seven, _duration(data.duration_ms), _lines(data.lines_added, data.lines_removed)]
    tier_two = [context, cost, worktree, agent]

    full = _join([*always, *tier_two, *tier_three])
    if _visible_length(full) <= width:
        return full
    folded = _fit([*always, *tier_two], tier_three, width)
    if _visible_length(folded) <= width:
        return folded
    return _fit(always, [worktree, agent, context, cost], width)


def statusline_width(environ: Mapping[str, str], tty_columns: Callable[[], int | None]) -> int:
    """Return the width to fold the line to, deciding like the script.

    `COLUMNS` when it is a positive integer above 80; otherwise the terminal's columns
    when positive (the script trusts them even when narrow); otherwise 200.
    """
    try:
        columns = int(environ.get("COLUMNS", ""))
    except ValueError:
        columns = 0
    if columns > _NARROW:
        return columns
    return tty_columns() or _DEFAULT_WIDTH
