"""Quota lines and the "limit around" projection (spec 7.4)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

_WINDOW = timedelta(minutes=30)
_LIMIT_PCT = 100.0
_WARN_PCT = 50
_ALERT_PCT = 80


@dataclass(frozen=True, slots=True, kw_only=True)
class QuotaLine:
    """The quota figures to show; `peak` is the peak-hours text, empty when unknown."""

    five_hour_pct: float | None
    five_hour_resets_at: datetime | None
    seven_day_pct: float | None
    seven_day_resets_at: datetime | None
    limit_at: datetime | None
    peak: str


def _current_cycle(samples: Sequence[tuple[datetime, float]]) -> Sequence[tuple[datetime, float]]:
    """Return the samples since the last drop of the percentage (a drop is a reset)."""
    start = 0
    for index in range(1, len(samples)):
        if samples[index][1] < samples[index - 1][1]:
            start = index
    return samples[start:]


def projected_limit(
    samples: Sequence[tuple[datetime, float]], *, resets_at: datetime | None, now: datetime
) -> datetime | None:
    """Return when a least-squares line through the recent samples reaches 100 %.

    Only the samples of the last 30 minutes before `now`, since the last drop of the
    percentage, count. The result is None without two samples at distinct instants, with
    a slope that is not positive, or when the limit is not after `now` and before `resets_at`.
    """
    recent = [(at, pct) for at, pct in samples if now - _WINDOW <= at <= now]
    cycle = _current_cycle(recent)
    if len(cycle) < 2:  # noqa: PLR2004 — a line needs two points
        return None
    origin = cycle[0][0]
    xs = [(at - origin).total_seconds() for at, _ in cycle]
    ys = [pct for _, pct in cycle]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / spread
    if slope <= 0:
        return None
    seconds = mean_x + (_LIMIT_PCT - mean_y) / slope
    limit = origin + timedelta(seconds=seconds)
    if limit <= now or (resets_at is not None and limit >= resets_at):
        return None
    return limit


def quota_level(pct: float) -> str:
    """Return "ok" under 50, "warn" from 50 to under 80, "high" from 80 on."""
    if pct >= _ALERT_PCT:
        return "high"
    return "warn" if pct >= _WARN_PCT else "ok"


def _part(label: str, pct: float | None, resets: str | None) -> str:
    if pct is None:
        return ""
    text = f"{label} {round(pct)}%"  # half to even, like the status line
    return text if resets is None else f"{text} · resets {resets}"


def quota_lines(line: QuotaLine, *, local: tzinfo) -> list[str]:
    """Return the quota lines to show: 5 h, 7 d and the peak hours; unknown parts are omitted."""
    five_reset = (
        None
        if line.five_hour_resets_at is None
        else line.five_hour_resets_at.astimezone(local).strftime("%H:%M")
    )
    seven_reset = (
        None
        if line.seven_day_resets_at is None
        else _weekday(line.seven_day_resets_at.astimezone(local))
    )
    five = _part("5h", line.five_hour_pct, five_reset)
    if five and line.limit_at is not None:
        limit = line.limit_at.astimezone(local).strftime("%H:%M")
        five = f"{five} · limit around {limit} at this rate"
    lines = [five, _part("7d", line.seven_day_pct, seven_reset), line.peak]
    return [text for text in lines if text]


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _weekday(at: datetime) -> str:
    return f"{_DAYS[at.weekday()]} {at:%H:%M}"
