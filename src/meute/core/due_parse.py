"""Parsing of due tokens such as `tomorrow`, `mon-9am`, `+2h` or `2026-10-20`."""

import re
from datetime import UTC, date, datetime, time, timedelta

from meute.core.task import Due, DueAt, DueDate

_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TONIGHT = time(18, 0)
_NOON = 12

_WEEKDAY_TIME = re.compile(r"(?P<day>[a-z]{3})-(?P<hour>[0-9]{1,2})(?P<half>am|pm)")
_DELTA = re.compile(r"\+(?P<count>[0-9]{1,4})(?P<unit>[hmd])")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_ISO_DATETIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}")


def parse_due(token: str, now: datetime) -> Due | None:
    """Parse a due token (without the leading `>`), relative to `now`.

    Keywords are case-insensitive and read in the time zone of `now`. Hours are
    real time, days are wall-clock time, and a local time that does not exist
    (spring DST gap) is shifted forward by an hour.

    Args:
        token: The token, e.g. `tomorrow`, `fri-2pm`, `+30m`, `2026-10-20T14:00`.
        now: The current aware time, in the zone used to read the token.

    Returns:
        The due, or None when the token is not a valid due.
    """
    try:
        return _parse(token, now)
    except OverflowError:
        return None


def _parse(token: str, now: datetime) -> Due | None:
    if _ISO_DATE.fullmatch(token):
        return _iso_date(token)
    if _ISO_DATETIME.fullmatch(token):
        return _iso_datetime(token, now)
    word = token.lower()
    if (match := _WEEKDAY_TIME.fullmatch(word)) and match["day"] in _WEEKDAYS:
        return _weekday_time(match["day"], int(match["hour"]), match["half"], now)
    if match := _DELTA.fullmatch(word):
        return _delta(int(match["count"]), match["unit"], now)
    return _keyword(word, now)


def _keyword(word: str, now: datetime) -> Due | None:
    today = now.date()
    if word == "tomorrow":
        return DueDate(day=today + timedelta(days=1))
    if word == "tonight":
        return local_due(today, _TONIGHT, now)
    if word in _WEEKDAYS:
        return DueDate(day=_next_weekday(word, today))
    return None


def _weekday_time(name: str, hour: int, half: str, now: datetime) -> DueAt | None:
    if not 1 <= hour <= _NOON:
        return None
    pm_offset = _NOON if half == "pm" else 0
    return local_due(_next_weekday(name, now.date()), time(hour % _NOON + pm_offset), now)


def _next_weekday(name: str, today: date) -> date:
    ahead = (_WEEKDAYS.index(name) - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def local_due(day: date, at: time, now: datetime) -> DueAt:
    """Return the due at the wall-clock `at` of `day` in the zone of `now`.

    A time in the spring DST gap is shifted forward by an hour.
    """
    return DueAt(at=datetime.combine(day, at, tzinfo=now.tzinfo))


def _delta(count: int, unit: str, now: datetime) -> DueAt | None:
    if count == 0:
        return None
    if unit == "d":
        return local_due(now.date() + timedelta(days=count), now.time(), now)
    step = timedelta(hours=count) if unit == "h" else timedelta(minutes=count)
    return DueAt(at=now.astimezone(UTC) + step)


def _iso_date(token: str) -> DueDate | None:
    try:
        return DueDate(day=date.fromisoformat(token))
    except ValueError:
        return None


def _iso_datetime(token: str, now: datetime) -> DueAt | None:
    try:
        local = datetime.fromisoformat(token)
    except ValueError:
        return None
    return local_due(local.date(), local.time(), now)
