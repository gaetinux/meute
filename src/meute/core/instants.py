"""Conversion and formatting of instants: every datetime in the core is aware."""

import re
from datetime import UTC, datetime

from meute.core.errors import InvalidInput

_DB_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
_ZONED = re.compile(r"(?P<local>\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\[(?P<zone>[^\]]+)\]")


def utc_now() -> datetime:
    """Return the current instant, aware, in UTC."""
    return datetime.now(UTC)


def to_db(at: datetime) -> str:
    """Return the fixed-width UTC text stored in the database (27 characters).

    Raises:
        ValueError: `at` is naive.
    """
    if at.tzinfo is None:
        message = "cannot store a naive datetime"
        raise ValueError(message)
    return at.astimezone(UTC).strftime(_DB_FORMAT)


def from_db(text: str) -> datetime:
    """Parse the text produced by `to_db` into an aware UTC datetime."""
    return datetime.strptime(text, _DB_FORMAT).replace(tzinfo=UTC)


def format_instant(at: datetime) -> str:
    """Return the JSON form of an instant, e.g. `2026-10-15T08:00:00Z`.

    Microseconds appear only when they are not zero.
    """
    utc = at.astimezone(UTC)
    return utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds").replace(
        "+00:00", "Z"
    )


def parse_zoned(text: str) -> datetime:
    """Parse `2026-10-14T10:30[Europe/Paris]` into an aware datetime in that zone.

    Raises:
        InvalidInput: the text has another shape or the zone is unknown.
    """
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError  # noqa: PLC0415 — keeps ingest start-up light

    match = _ZONED.fullmatch(text)
    if match is None:
        message = f"invalid zoned time: {text}"
        raise InvalidInput(message)
    try:
        zone = ZoneInfo(match["zone"])
        local = datetime.fromisoformat(match["local"])
    except (ZoneInfoNotFoundError, ValueError) as error:
        message = f"invalid zoned time: {text}"
        raise InvalidInput(message) from error
    return local.replace(tzinfo=zone)
