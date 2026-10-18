"""Quota lines and the "limit around" projection (spec 7.4)."""

import math
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, tzinfo

from meute.core.statusline import StatuslineData

PROJECTION_WINDOW = timedelta(minutes=30)
"""How far back the samples count for the "limit around" projection."""
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


def current_quota(sample: StatuslineData, *, now: datetime) -> StatuslineData:
    """Return `sample` without the windows whose reset is not after `now`.

    A window that has reset says nothing about the current one: its percentage and reset are
    dropped until a newer sample arrives. A window with no known reset is kept.
    """
    if sample.five_hour_resets_at is not None and sample.five_hour_resets_at <= now:
        sample = replace(sample, five_hour_pct=None, five_hour_resets_at=None)
    if sample.seven_day_resets_at is not None and sample.seven_day_resets_at <= now:
        sample = replace(sample, seven_day_pct=None, seven_day_resets_at=None)
    return sample


def _current_cycle(samples: Sequence[tuple[datetime, float]]) -> Sequence[tuple[datetime, float]]:
    """Return the samples since the last drop of the percentage (a drop is a reset)."""
    start = 0
    for index in range(1, len(samples)):
        if samples[index][1] < samples[index - 1][1]:
            start = index
    return samples[start:]


def _crossing_seconds(cycle: Sequence[tuple[datetime, float]]) -> float | None:
    """Return the seconds after the first sample at which the fitted line reaches 100 %."""
    origin = cycle[0][0]
    xs = [(at - origin).total_seconds() for at, _ in cycle]
    ys = [pct for _, pct in cycle]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    spread = sum((x - mean_x) ** 2 for x in xs)
    if spread == 0:
        return None
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / spread
    if not slope > 0:  # also false for NaN
        return None
    seconds = mean_x + (_LIMIT_PCT - mean_y) / slope
    return seconds if math.isfinite(seconds) else None


def projected_limit(
    samples: Sequence[tuple[datetime, float]], *, resets_at: datetime | None, now: datetime
) -> datetime | None:
    """Return when a least-squares line through the recent samples reaches 100 %.

    Only the samples of the last 30 minutes before `now`, since the last drop of the
    percentage, count. The result is None without two samples at distinct instants, with
    a slope that is not positive, or when the limit is not after `now` and before `resets_at`.
    It never raises: a limit too far away for a datetime is None.
    """
    recent = [(at, pct) for at, pct in samples if now - PROJECTION_WINDOW <= at <= now]
    cycle = _current_cycle(recent)
    if len(cycle) < 2:  # noqa: PLR2004 — a line needs two points
        return None
    seconds = _crossing_seconds(cycle)
    origin = cycle[0][0]
    # Compare in seconds first: a near-flat slope gives a time no datetime can hold.
    if seconds is None or seconds <= (now - origin).total_seconds():
        return None
    if resets_at is not None and seconds >= (resets_at - origin).total_seconds():
        return None
    try:
        return origin + timedelta(seconds=seconds)
    except OverflowError:  # no reset to bound a near-flat slope: the limit is out of range
        return None


def quota_level(pct: float) -> str:
    """Return "ok" under 50, "warn" from 50 to under 80, "high" from 80 on."""
    if pct >= _ALERT_PCT:
        return "high"
    return "warn" if pct >= _WARN_PCT else "ok"


_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _weekday(at: datetime) -> str:
    return f"{_DAYS[at.weekday()]} {at:%H:%M}"


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
