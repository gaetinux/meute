"""The local time zone."""

from collections.abc import Mapping
from datetime import UTC, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOCALTIME = Path("/etc/localtime")


def local_zone(environ: Mapping[str, str]) -> tzinfo:
    """Return the local IANA zone: `TZ` if valid, else `/etc/localtime`, else UTC.

    The zone is never a fixed offset, so `>+1d` and `>tonight` follow daylight saving time.
    """
    name = environ.get("TZ", "").removeprefix(":")
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):  # ZoneInfoNotFoundError is a KeyError
            pass
    try:
        with _LOCALTIME.open("rb") as handle:
            return ZoneInfo.from_file(handle)
    except (ValueError, OSError):
        return UTC
